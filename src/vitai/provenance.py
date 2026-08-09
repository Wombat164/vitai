"""Provenance is a CHAIN, not a source string (#35, #51).

The mistake this exists to stop, in one line: **an activity present in both
Polar and Strava is one measurement seen twice, not two measurements
agreeing.**

Platforms are mostly SINKS. Strava, Google Health and Apple Health
predominantly receive data recorded elsewhere, so treating their agreement as
corroboration double-counts a single reading and raises confidence on the
strength of nothing. Independent instruments corroborate; a sync pipeline
does not - it is the same instrument at the other end of a wire.

It was found by making the mistake twice. A walk read 2.226 km from a Strava
export and 2.23 km from Polar, and that near-agreement was taken as two
sources concurring; it is one Polar Pacer Pro reading. And the resolution
layer emitted `fitbit-api+mfp-export`, which reads as a union of independent
sources when MyFitnessPal had received those weights FROM Fitbit.

## The three parts of a chain

    reality -> origin -> hop -> hop -> ... -> terminus

- **origin** - what observed reality: a device, or a person typing. This is
  the only part corroboration may key on.
- **path** - the ordered hops it travelled. Every hop may add, change, infer
  or delete, so this is where trust is lost.
- **terminus** - how it entered this record. That is the existing `source`
  field, which answers only this and was being asked to answer all three.

## Two consequences that are easy to state and easy to get wrong

**Corroboration requires divergent ORIGINS.** Same origin, different path is
one measurement. `witnesses` must count distinct origins, not rows.

**Trust is bounded by the WEAKEST hop, not the origin.** A device-measured
weight that passed through a vendor which rounds, re-derives or back-fills is
no longer device-measured, however good the device was.

## Unstated is not absent

A row with no `origin` is in a different state from one whose origin is
recorded as unknown. Collapsing them asserts something nobody established -
and an unknown origin must never count as an independent source, or the
Takeout import (where the originating device is often lost entirely) would
manufacture corroboration out of missing data.
"""

from __future__ import annotations

from .vocab import meta, registry, resolve

# How hops are written in `path`: an ordered, arrow-separated list of names.
# Flat text rather than nested JSON for the same reason a restriction is
# (#18): it stays writable by hand and by a screenshot-reading skill, and the
# dataset stays one flat object per line.
SEPARATOR = ">"
UNKNOWN = "unknown"


def hops(path: object) -> list[str]:
    """The ordered hop names in a path, or [] for an empty one."""
    if path is None or not str(path).strip():
        return []
    return [h.strip() for h in str(path).split(SEPARATOR) if h.strip()]


def role_of(hop: object) -> str:
    """The registry role for a hop name, or `unknown` if unrecognised.

    Real hops are named for their vendor: `fitbit-api`, `mfp-export`,
    `polar-flow`. So a bare-role lookup alone would classify almost every real
    chain as unknown, and a trust signal that is always "unknown" tells nobody
    anything. The LAST token of the name is therefore tried against the role
    vocabulary - `fitbit-api` ends in `api`, `mfp-export` ends in `export`.

    That is a spelling rule over declared role names, not a vendor list and
    not a fuzzy match: it can only ever reach a role the registry already
    declares. A name whose last token names nothing stays `unknown`.

    The one direction that could cost something is promoting a hop to a
    NON-mutating role it does not deserve - a mutating step called
    `something-watch` would read as a device. Named here rather than guarded
    against, because the alternative (suffix-matching only mutating roles)
    makes every device hop unknown, which is the failure this exists to fix.
    """
    if (direct := resolve("provenance", "roles", hop)) is not None:
        return direct
    tail = str(hop or "").replace("_", "-").replace(" ", "-").split("-")[-1]
    return resolve("provenance", "roles", tail) or UNKNOWN


def may_mutate(hop: object) -> bool:
    """Could this hop have changed the value on its way through?"""
    entry = meta("provenance", "roles", hop)
    return bool(entry.get("may_mutate", True))


def roles() -> list[str]:
    return sorted(registry("provenance").get("roles") or {})


def origin_of(rec: dict) -> str | None:
    """The instrument that observed this value, or None if unstated.

    None means NOBODY SAID, which is not the same as `unknown` meaning
    "recorded, and we could not tell". Both refuse to corroborate, but only
    one of them is a gap someone could still fill.
    """
    value = rec.get("origin")
    return str(value) if value not in (None, "") else None


def is_independent(rec: dict) -> bool:
    """May this row's origin count as a distinct witness?

    An unstated or unknown origin may not. That is the guard which stops a
    Google Takeout import - where the originating device is frequently lost -
    from manufacturing corroboration out of missing data.
    """
    origin = origin_of(rec)
    return origin is not None and origin != UNKNOWN


def _channel(rec: dict) -> str | None:
    """The route a row arrived by, or None when it does not name one.

    NONE RATHER THAN `unknown`, and the distinction is the same one this
    module makes everywhere else: an unstated channel is nobody saying, not a
    channel called "unknown". Folding them together let two rows merge on the
    strength of what they BOTH failed to say, which is the collapse
    `shares_origin` refuses one function below - the engine does not get to
    assume two anonymous rows are the same reading.
    """
    source = rec.get("source")
    return str(source) if source not in (None, "") else None


def distinct_origins(recs: list[dict]) -> set[str]:
    """The genuinely independent origins among these claims."""
    return {str(origin_of(r)) for r in recs if is_independent(r)}


def independent_witnesses(recs: list[dict]) -> int:
    """How many INDEPENDENT observations these claims represent.

    Not `len(recs)`. Five rows carrying one watch's reading through five
    platforms are one witness, and reporting five is the false confidence
    this whole module exists to prevent.

    Rows with no usable origin are counted by the CHANNEL they arrived by, so
    a record with no provenance at all still reports one witness per distinct
    source rather than collapsing to nothing - a legitimately un-annotated
    history keeps whatever independence it can demonstrate - while two rows
    down one channel stay one witness however many times they are restated.

    A SUPERSEDED ROW IS NOT HERE TO BE COUNTED. `retire` drops it at load, so
    a correction that applied never reaches this function. A correction that
    did NOT apply, because its reference matched no line, is a different
    defect and is filed as one: the row is still live, and counting it is
    correct behaviour on incorrect data.
    """
    # A DERIVED VALUE NEVER CORROBORATES ITS OWN INPUTS (#170), and the count
    # below is what enforces it. Derived rows contribute NOTHING OF THEIR OWN.
    # What they contribute is the observations their lineage names, counted
    # once across all of them together: a value computed from a reading is
    # that reading wearing arithmetic, so however many rows are wrapped around
    # one observation, the observation is still one witness.
    #
    # Counted ACROSS clusters rather than per cluster, because per-cluster
    # counting let arithmetic manufacture witnesses: two readings from one
    # scale are one witness, and two values each computed from one of them
    # would have been two.
    #
    # A row reference names `dataset:date:source`, and `source` is the same
    # field the rows themselves carry, so this compares like with like. By
    # SOURCE and not by date, matching how `distinct_origins` treats the rows
    # here: two readings from one scale on two mornings are one witness, so
    # two values computed from them must be one witness too, or the same
    # observation counts differently depending on whether arithmetic was
    # applied to it. A reference this cannot parse falls back to one witness
    # for its cluster, which is the answer that assumes least.
    clusters = derivation_groups(recs)
    derived_ids = {id(r) for group in clusters for r in group}
    plain = [r for r in recs if id(r) not in derived_ids]

    named, unparsed = set(), 0
    for group in clusters:
        refs = {str(x) for row in group for x in (row.get("derived_from") or [])}
        sources = {p[2] for p in (r.split(":") for r in refs) if len(p) >= 3}
        if sources:
            named |= sources
        else:
            unparsed += 1

    # An input that is ALSO one of the rows here is already counted below, by
    # its own origin. Counting it again as something the derivation names
    # would corroborate an observation with a restatement of itself.
    here = {str(r.get("source")) for r in plain if r.get("source")}
    from_lineage = len(named - here) + unparsed

    # SOURCES, NOT ROWS (#211). A row whose origin is unstated used to count as
    # its own witness on top of every named origin, so two rows from ONE source
    # reported two independent sources - and correcting a row, which appends a
    # second one, INFLATED the evidence for the value being corrected. The more
    # carefully someone kept their record, the better witnessed it looked.
    #
    # An unstated origin cannot be told from another unstated origin by
    # instrument, so the only thing distinguishing those rows is the channel
    # they arrived by. Two deliveries down one channel are one witness. And a
    # channel already represented by a row whose instrument IS named adds
    # nothing: the same source, once with an origin and once without, is one
    # source either way.
    #
    # This is the shared-influence rule the metrology literature states for
    # quantities entering a result by two routes: enter it once, and make the
    # shared node explicit rather than fudging the combination afterwards.
    known = distinct_origins(plain)
    named_channels = {c for r in plain if is_independent(r)
                      and (c := _channel(r)) is not None}
    anon = [r for r in plain if not is_independent(r)]
    anon_channels = {c for r in anon if (c := _channel(r)) is not None}
    # A row that names NEITHER an instrument nor a channel stands alone: there
    # is nothing to dedupe it against, and merging two of them would assert a
    # shared origin nobody stated. Counted individually, which is what the
    # un-annotated history this rule protects actually needs.
    unattributed = sum(1 for r in anon if _channel(r) is None)
    base = len(known) + len(anon_channels - named_channels) + unattributed
    return base + from_lineage


def shares_origin(a: dict, b: dict) -> bool:
    """Do these two claims come from the same instrument?

    False when either origin is unstated or unknown - the engine does not get
    to assume two anonymous rows are the same reading any more than it gets
    to assume they are different.
    """
    return (is_independent(a) and is_independent(b)
            and origin_of(a) == origin_of(b))


def same_witness(a: dict, b: dict) -> bool:
    """Would counting these two separately count one observation twice?

    THE PAIRWISE FORM OF THE COUNTING RULE (#211), and it exists so the two
    cannot drift. `independent_sources` said one witness while the resolution
    row beside it called the same pair "independent observations", because the
    count deduped by channel and the label still keyed on instrument alone.
    Two fields, one question, two answers.

    Instruments decide it when both are named. Where either is unstated the
    instrument cannot be compared, so the channel is the only independence
    either row can demonstrate - and a row naming no channel demonstrates
    none, so it stands alone rather than merging with another silence.
    """
    if is_independent(a) and is_independent(b):
        return origin_of(a) == origin_of(b)
    channel = _channel(a)
    return channel is not None and channel == _channel(b)


def derivation_groups(recs: list[dict]) -> list[list[dict]]:
    """Derived rows clustered by the inputs they stand on.

    Transitive: a row from x and y, a row from y and z, and a row from z and w
    are ONE cluster, because each link is the same observation reappearing
    with arithmetic on top. Chaining is the point - a two-hop derivation is
    still not a second look at the athlete.
    """
    groups: list[tuple[set, list[dict]]] = []
    for rec in recs:
        lineage = {str(x) for x in (rec.get("derived_from") or [])}
        if not lineage:
            continue
        hit = [g for g in groups if g[0] & lineage]
        merged_refs, merged_rows = set(lineage), [rec]
        for g in hit:
            merged_refs |= g[0]
            merged_rows += g[1]
            groups.remove(g)
        groups.append((merged_refs, merged_rows))
    return [rows for _refs, rows in groups]


# --- how a value was acquired (#77/#78) ---------------------------------------

READERS = ("athlete", "model", "human-other")


ACTIVE, PASSIVE = "active", "passive"


def capture_of(rec: dict) -> str:
    """The acquisition method, resolved through the registry.

    An unrecognised value lands in `unknown` rather than erroring: a capture
    method nobody here imagined is a gap in the registry, not a fault in the
    athlete's record - and `unknown` already assumes the costly side of both
    its properties.
    """
    return resolve("capture", "capture", rec.get("capture")) or UNKNOWN


def initiative_of(rec: dict) -> str:
    """Did the athlete's own action produce this value: `active`, `passive`,
    `derived` or `unknown` (#146).

    The axis `capture` could not answer. A photo of a console and a BLE read
    of the same console are one origin and two captures, and they are also two
    completely different facts about whether anybody was there.
    """
    from .vocab import registry

    entry = (registry("capture").get("capture") or {}).get(capture_of(rec)) or {}
    return str(entry.get("initiative") or UNKNOWN)


def channel_liveness(rows: list[dict], on: str) -> dict:
    """When each kind of channel last said anything, on or before `on`.

    Returns `{initiative: {"last_seen": date|None, "quiet_days": int|None,
    "rows": n}}` for `active` and `passive` only, plus `contrast` - the days
    between them where both have spoken and the passive side is the later one.

    WHAT THIS IS FOR. An engine can see what arrived and not whether anybody
    was there when it did. A record where the watches keep syncing and every
    line the athlete wrote himself stopped a month ago is not the same record
    as one where nothing is happening, and the difference is free: it is
    already in `capture`, one registry field away.

    AN OBSERVATION, NEVER A READING OF IT. It reports two dates and the gap
    between them. It does not say engagement, adherence, motivation or
    concern, and it must never grow a threshold that decides when the gap
    becomes one of those - the record cannot tell a bereavement from a holiday
    from a phone left in a drawer, and a persona in this corpus exists
    precisely to prove that guessing is wrong even when the guess is right.
    Silence is absence of information: not compliance, because nothing was
    adhered to, and not refusal, because nothing was declined.

    `derived` AND `unknown` ARE EXCLUDED. Arithmetic is not a person and not a
    sensor, and an unstated capture is a gap in the record rather than a quiet
    channel - counting it would let a record that has never written `capture`
    report every channel as silent, which is a statement about the athlete
    made out of a statement about the schema.
    """
    from datetime import date as _date

    seen: dict[str, list[str]] = {ACTIVE: [], PASSIVE: []}
    for rec in rows:
        when = str(rec.get("date") or "")
        if not when or when > on:
            continue
        side = initiative_of(rec)
        if side in seen:
            seen[side].append(when)

    out: dict[str, object] = {}
    for side, dates in seen.items():
        last = max(dates) if dates else None
        quiet = None
        if last:
            try:
                quiet = (_date.fromisoformat(on) - _date.fromisoformat(last)).days
            except ValueError:
                quiet = None
        out[side] = {"last_seen": last, "quiet_days": quiet, "rows": len(dates)}

    # THE CONTRAST, and only where both sides have actually spoken. A record
    # with no active rows at all has not gone quiet - it never used that
    # channel, and reporting a gap would invent a history it does not have.
    active, passive = out[ACTIVE], out[PASSIVE]
    contrast = None
    if (active["last_seen"] and passive["last_seen"]
            and passive["quiet_days"] is not None
            and active["quiet_days"] is not None
            and active["quiet_days"] > passive["quiet_days"]):
        contrast = active["quiet_days"] - passive["quiet_days"]
    out["contrast_days"] = contrast
    return out


def may_transcribe(rec: dict) -> bool:
    """Did a human or a model READ a display to produce this value?"""
    return bool(meta("capture", "capture", capture_of(rec)).get(
        "may_transcribe", True))


def has_artifact(rec: dict) -> bool:
    """Can evidence for this value exist and be looked at again?"""
    return bool(meta("capture", "capture", capture_of(rec)).get(
        "has_artifact", False))


# The worst value on the scale, for a registry entry that predates the field.
MOST_RESTATED = 2


def states_capture(rec: dict) -> bool:
    """Did this line SAY how the value was acquired?

    UNSTATED IS NOT ABSENT, which this module's own header insists on and
    which the first cut of the rank ignored: it defaulted an unstated capture
    to the worst value, so a line that said nothing lost to a line that said
    `file_export`. That is not the costly side, it is the wrong side - the
    cost lands on the OTHER claim, and penalising the silent row PROMOTES the
    stale annotated one. A food log re-exported the next morning with no
    capture written lost to the previous morning's annotated export, which is
    the 1,700 kcal error #70 exists to prevent, reintroduced through the
    fix for #140.
    """
    return resolve("capture", "capture", rec.get("capture")) is not None


def restatements(rec: dict) -> int:
    """How many times a PERSON restated this number between the instrument
    and the record (#140).

    Not a quality score. `ble` and `file_export` both sit at 0 though their
    virtues differ completely, and nothing here says which is better - see
    `semantics/capture.toml`, which exists partly to stop that reading.

    THE OTHER EVIDENCE ROUTE is `resolution.restatement_runs`, which detects
    the same phenomenon from the SHAPE of a series when the record says
    nothing about capture at all. This one ranks what the record SAYS; that
    one asks why a quantity that should move did not. Neither replaces the
    other: a record can be wrong about its capture, and a restated series can
    be honestly labelled.

    It exists because the resolution ladder had nothing to rank by when a lie
    and the truth SHARE A SOURCE. An athlete who logs a weight from memory and
    records it as `source: scale` produces two claims precedence cannot tell
    apart, and no configuration helps. This ranks what the record SAYS about
    how the value was acquired, so an honestly recorded "I remembered this"
    loses to a device reading - which is all the athlete meant by writing it
    down that way. It is not lie detection and must never become it.
    """
    return int(meta("capture", "capture", capture_of(rec)).get(
        "restatements", MOST_RESTATED))


def transcribed_by(rec: dict) -> str | None:
    """Who did the reading, where the capture needed one."""
    who = rec.get("read_by")
    return str(who) if who else None


# DELIBERATELY UNRANKED: `read_by`. #140 notes that third-party capture
# carries no rank either - `derek`'s wife enters rows on his behalf - and the
# answer is not to rank the people. A third party reading a display is still
# a display reading, so `capture` already carries what resolution needs, and
# a training log that sorted its owner's household by reliability would be
# doing something no finding here asks for.


def capture_problems(rec: dict) -> list[str]:
    """A transcribing capture with nobody named to have done the reading."""
    out: list[str] = []
    written = rec.get("capture")
    if written is not None and resolve("capture", "capture", written) is None:
        out.append(f"unknown capture {written!r} - one of "
                   f"{', '.join(sorted(registry('capture')['capture']))}")
    if (who := rec.get("read_by")) is not None and str(who) not in READERS:
        out.append(f"'read_by' is one of {', '.join(READERS)}, got {who!r}")
    if who is not None and written is None:
        # The mirror of "a path needs an origin to have travelled from": a
        # reader with nothing said to have been read is a claim about an
        # acquisition that the row does not describe.
        out.append("'read_by' names who read a display, so it needs a "
                   "'capture' that involved reading one")
    # A photo read by nobody is not a reading, it is an unattributed one - and
    # a photo read by a MODEL is an inference over an artifact rather than a
    # measurement, which is the whole reason the field exists (#49's family).
    if written is not None and may_transcribe(rec) and not rec.get("read_by"):
        if capture_of(rec) != UNKNOWN:
            out.append(f"capture {capture_of(rec)!r} means someone read a "
                       "display, so 'read_by' must say who: "
                       f"{', '.join(READERS)}")
    return out
# --- the source catalog (#79) ---------------------------------------------------

CATALOG_OTHER = "other"

# Words that name how a value ARRIVED rather than what observed it. They
# belong to `capture`, and a source string ending in one is still naming the
# instrument in front of it.
CHANNEL_SUFFIXES = frozenset({
    "export", "api", "takeout", "sync", "connector", "csv", "dump",
    "archive", "download", "file"})


def resolve_source(written: object) -> str:
    """Catalogued instrument for whatever was written, or `other`.

    NEVER an error. An uncatalogued instrument is a gap in the registry, not a
    fault in the athlete's record - and a private source name (someone's own
    spreadsheet, their own gym) resolves here precisely so it never has to
    appear in a public file.
    """
    if written is None or str(written).strip() == "":
        return UNKNOWN
    if (found := resolve("sources", "sources", written)) is not None:
        return found
    # Source strings routinely carry the CHANNEL as a suffix - `mfp-export`,
    # `fitbit-takeout`, `strava-api`. That suffix answers `capture`, not
    # "which instrument", so it is stripped and the instrument looked up
    # again. A spelling rule over declared names, not a fuzzy match: it can
    # only reach an entry that already names the base.
    base = str(written).replace("_", "-").rsplit("-", 1)
    if len(base) == 2 and base[1].lower() in CHANNEL_SUFFIXES:
        if (found := resolve("sources", "sources", base[0])) is not None:
            return found
    return CATALOG_OTHER


def source_kind(written: object) -> str:
    """What KIND of thing observed this - a watch, a scale, a console, a
    person. Google Fit's `Device.type` axis, extended.

    An uncatalogued source still gets a kind where the name says one: a row
    whose source is written `scale` or `watch` is not a catalogued instrument,
    but it is plainly not a person either. That is exactly the shape the issue
    asked for - `other` PLUS a kind - rather than a `generic-scale` entry that
    would multiply the catalog by the size of the kind axis.
    """
    catalogued = meta("sources", "sources", resolve_source(written)).get("kind")
    if catalogued and catalogued != UNKNOWN:
        return catalogued
    return resolve("sources", "kinds", written) or UNKNOWN


def cannot_observe(written: object) -> set[str]:
    """Fields no instrument of this KIND can physically produce.

    A DENY list, not a whitelist. Written the other way round it turned every
    omission into a false accusation - an Oura ring does report calories, a
    hand-typed row can carry a heart rate read off a watch, a relaying app
    carries whatever it received. An omission here produces silence instead,
    which is the direction that costs nothing.

    Held at the kind rather than the instrument because that is the level at
    which the claim is confidently true of EVERY member.
    """
    kind = source_kind(written)
    return set(meta("sources", "kinds", kind).get("cannot") or [])


def denied_fields() -> set[str]:
    """Every field any kind is declared unable to observe.

    A field no kind denies is never checked, so adding a schema column cannot
    retroactively accuse anybody.
    """
    return {f for entry in registry("sources")["kinds"].values()
            for f in entry.get("cannot") or []}


def impossible_claims(rec: dict, fields: list[str]) -> list[str]:
    """Fields this row states that its own instrument cannot observe (#79).

    Not a resolution tie to adjudicate - a tie is two instruments disagreeing,
    and this is one instrument claiming something it has no sensor for: a
    scale reporting distance, a rowing console reporting sleep, a food log
    reporting heart rate. Nothing caught that before, because `source` was
    free text and nothing knew what a scale is.

    Silent unless the source's KIND is known and denies the field outright,
    so an uncatalogued instrument is never accused of anything.
    """
    denied = cannot_observe(rec.get("source"))
    if not denied:
        return []
    return [f for f in fields
            if f in denied and rec.get(f) is not None]


# --- was it MEASURED at all? (#49, #88) ---------------------------------------
#
# The orthogonal question to origin and capture. Those say WHICH instrument and
# HOW it reached us; this says whether the number was ever observed.
#
# A model output arriving in a field whose name and type imply measurement is
# invisible by construction: `kcal_out: 1728` on two different dates is BMR
# modelling, because the tracker was not worn - and nothing downstream can
# tell. Five separate instances turned up in ONE import, which is what makes
# it a rule rather than three patches.
#
# The harm is specific and not tidiness. An inflated burn reaching a deficit
# makes the arithmetic read ON TARGET while the scale goes up, and the athlete
# is told to hold a plan that is not working. Labelling it in a note is not
# enforcement: prose is not a thing code can check.
#
# `modelled` is a flat list of the FIELDS on this row that are model outputs,
# because the distinction is per-field - one row can carry a measured step
# count and an estimated burn.

# How a CATEGORICAL label was arrived at (#88). Not the same question as
# `capture`: a vendor classifier is not an acquisition method, it is an
# inference over sensor data nobody outside the vendor ever sees. In one live
# record 1,093 of 1,502 session types were a classifier's guess and the record
# could not tell them from the 409 the athlete asserted.
TYPE_SOURCES = ("athlete-stated", "device-recorded", "vendor-classified",
                "engine-inferred")


def modelled_fields(rec: dict) -> set[str]:
    """Fields on this row that are model outputs rather than observations."""
    written = rec.get("modelled")
    if not written or not str(written).strip():
        return set()
    return {f.strip() for f in str(written).replace(",", " ").split() if f.strip()}


def is_modelled(rec: dict, field: str) -> bool:
    return field in modelled_fields(rec)


def type_source(rec: dict) -> str | None:
    """How this row's categorical `type` was assigned, if stated."""
    written = rec.get("type_source")
    return str(written) if written else None


def value_kind_problems(rec: dict, keys: list[str]) -> list[str]:
    """Validation for the two ways a row can say a value was not observed."""
    out: list[str] = []
    for f in sorted(modelled_fields(rec)):
        if f == "modelled":
            out.append("'modelled' cannot name itself")
        elif f not in keys:
            out.append(f"'modelled' names {f!r}, which is not a field on this "
                       "dataset")
    if (t := rec.get("type_source")) is not None and str(t) not in TYPE_SOURCES:
        out.append(f"'type_source' is one of {', '.join(TYPE_SOURCES)}, "
                   f"got {t!r}")
    if rec.get("type_source") is not None and rec.get("type") is None:
        out.append("'type_source' says how a type was assigned, so it needs "
                   "a 'type'")
    return out


def trust_ceiling(rec: dict) -> str:
    """`device-measured` | `derived-in-transit` | `transcribed` |
    `unknown-transit`.

    A value is only device-measured if it reached us untouched. One hop that
    rounds, re-derives or back-fills breaks that claim - and a hop nobody
    recognises breaks it too, because the alternative is to assume a stranger
    was lossless.
    """
    # The ACQUISITION bounds the value just as a hop does, and for the same
    # reason: a photograph of a console read by a model is an inference over
    # an artifact, not a reading of an instrument. The origin is still the
    # console - what changes is what can be claimed about the number.
    #
    # Taken as the WEAKEST of the two signals, not the first one that matches.
    # Returning "transcribed" early let it MASK a worse condition: a photo
    # with no origin at all, or a chain containing a hop nobody recognises,
    # would have claimed more than the row deserves - which is this module's
    # own rule used against itself.
    levels = []
    if rec.get("capture") is not None and may_transcribe(rec):
        levels.append("transcribed")
    levels.append(_chain_ceiling(rec))
    return max(levels, key=TRUST_ORDER.index)


# Weakest LAST, so `max` over this order takes the least trustworthy signal.
TRUST_ORDER = ("device-measured", "derived-in-transit", "transcribed",
               "unknown-transit")


def _chain_ceiling(rec: dict) -> str:
    """What the ORIGIN and the hops alone allow, ignoring the acquisition."""
    if not is_independent(rec):
        return "unknown-transit"
    chain = hops(rec.get("path"))
    if not chain:
        return "device-measured"
    if any(role_of(h) == UNKNOWN for h in chain):
        return "unknown-transit"
    return ("derived-in-transit" if any(may_mutate(h) for h in chain)
            else "device-measured")


def describe(rec: dict) -> str:
    """The chain in one readable line, for a report or an explanation."""
    origin = origin_of(rec) or "unstated origin"
    chain = hops(rec.get("path"))
    if not chain:
        return f"{origin}, direct"
    named = " -> ".join(f"{h} ({role_of(h)})" for h in chain)
    return f"{origin} -> {named}"


def problems(rec: dict) -> list[str]:
    """Validation for the two provenance fields."""
    out: list[str] = []
    origin = rec.get("origin")
    if origin is not None and (not isinstance(origin, str) or not origin.strip()):
        out.append("'origin' names the instrument that observed the value, "
                   f"or null if nobody said (got {origin!r})")
    path = rec.get("path")
    if path is not None:
        if not isinstance(path, str) or not path.strip():
            out.append("'path' is an arrow-separated chain of hops "
                       f"(e.g. 'polar-flow{SEPARATOR}strava'), or null")
        elif origin in (None, ""):
            # A path with no origin describes a journey from nowhere, and it
            # would let an anonymous row look annotated.
            out.append("'path' records how a value travelled, so it needs an "
                       "'origin' to have travelled from")
    if rec.get("origin_evidence") is not None and not isinstance(
            rec.get("origin_evidence"), str):
        out.append("'origin_evidence' is the text a file declared "
                   "(e.g. 'TCX Creator: Polar Pacer Pro'), or null")
    return out
