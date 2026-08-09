"""Many claims, one canonical truth (G15) - the conservation golden rule.

A calorie is eaten once and burned once. When a watch says 2,443 kcal and a
calorie app says 2,844 kcal for the same day, the record does not hold both,
and it certainly does not hold 5,287. It holds ONE canonical value chosen by
precedence, with both claims retained as observations and the choice
explained.

This runs at build time, BEFORE any derivation. The rollup, verdicts,
contributions and the read model's primary tables consume canonical rows, and
raw claims are projected into companion `*_claims` tables for anyone who wants
to audit the adjudication.

ONE DOCUMENTED EXCEPTION, and it is narrow (#186). `daily.coverage` is read
RAW by `verdicts.open_day_in`, by the report's tripwire block and by the
intake floors, because it is not a measurement - it is a claim that a
measurement is not finished. Adjudicating it destroys it: a watch that syncs
steps and calls the day `full` outranks a nutrition app's lunchtime `partial`,
and the resolved row then reads `full` on the exact day the flag exists to
hear. A claim of openness is not refuted by a source that did not know.

That sentence was written here as "EVERYTHING downstream consumes canonical
rows" and left standing when the exception landed, which is the licence this
codebase keeps paying for. The general rule is unchanged and any NEW raw read
needs the same kind of argument written next to it: the field must be a claim
ABOUT a measurement rather than a measurement, and the reason precedence
destroys it must be stated.

Three rules do the work:

1. **Per-quantity precedence.** Each FIELD resolves independently by source
   rank: a day's canonical row is a field-wise merge of the best witness per
   quantity, never a sum of witnesses. The heart-rate device wins `kcal_out`
   while the food ledger wins `kcal_in`, on the same day, from different
   sources.
2. **Activity identity.** Two session claims are the same physical activity
   when their times intersect (or, lacking times, when type matches and
   duration/distance land inside tolerance bands). The richer claim becomes
   canonical; the other is corroboration and is excluded from totals. This is
   what stops one run logged on two platforms becoming two runs.
3. **Energy as attribution, not addition.** A device's daily `kcal_out`
   already CONTAINS its sessions' energy. Session kcal are attributions
   within the day; cross-app "exercise calories" are the same joules and are
   never re-added.

Violations surface as CONSERVATION TRIPWIRES and are never auto-fixed. If the
sessions burned more than the day did, something is double-counted or a
source is wrong, and silently smoothing that over would hide the very fault
the record exists to expose.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .clocks import comparable, is_aware, parse_time, stamp_instant
from .provenance import (TRUST_ORDER, capture_of, describe, distinct_origins,
                         independent_witnesses, restatements, same_witness,
                         shares_origin,
                         states_capture, trust_ceiling)

from .schema import KEYS, is_number

# One definition, in provenance.py, so the ladder cannot drift between the
# module that produces a level and the module that ranks it.
#
# `transcribed` sits below a vendor re-derivation on purpose: a hop that
# rounds or recomputes introduces a BOUNDED error, while a misread digit is
# unbounded - 3.1 and 31 differ by an order of magnitude and look equally
# plausible on a console. What could redeem it is the artifact, which is
# re-readable where a vendor's current model is not; storing that is #80.

# Datasets that carry competing observations. Policy datasets (goals,
# thresholds, context, achievements) are not claims about a measurement and
# resolve by effective date instead - see policy.py.
# `sets` is deliberately ABSENT (#97). It carries the full provenance suite
# and competes by source in every other sense, but this resolver's unit is one
# canonical record per DATE, and a set is not a per-date quantity: four sets of
# one exercise on one morning are four things that happened, not four claims
# about one. Adding it here collapsed a whole block into a single row.
#
# Doing it properly means keying resolution on the position tuple
# (session_start, exercise, block, round, set_index) the way #43 taught
# `sessions` to key on `activity_id` - which is its own increment. Until then
# a set's claims are kept exactly as recorded, which is the safe direction:
# nothing is merged, so nothing is lost.
RESOLVED_DATASETS = ("weight", "daily", "sessions", "measurements")

# Quantity class per dataset (P3). Anchors top the ladder: a tape measure or a
# DEXA read recalibrates a disagreeing estimate, never the reverse.
QUANTITY_CLASS = {
    "weight": "anchor",
    "measurements": "anchor",
    "daily": "measured_flow",
    "sessions": "measured_flow",
}

# Fuzzy activity-identity tolerances, lacking timestamps to intersect.
DURATION_RATIO = (0.8, 1.25)
DISTANCE_RATIO = (0.9, 1.1)

# The three linkage outcomes. POSSIBLE is the whole point: it is not a weaker
# MATCH, it is a refusal to decide, and it leaves both claims standing.
MATCH, POSSIBLE, DISTINCT = "match", "possible", "distinct"

# More than this many shape-alike claims of one type on one date is a routine,
# not a duplicate set. Three similar walks are three walks; nobody's tracker
# emits the same activity three times.
ROUTINE_THRESHOLD = 2
# Just outside those bands is where a near-miss duplicate hides - close enough
# to suspect, not close enough to merge. Flagged, never merged.
NEAR_MISS_SLACK = 0.15

# How far two high-precedence claims may differ before it is worth saying so.
DISAGREEMENT_TOLERANCE = 0.10
# Sessions may attribute slightly more than the day's measured burn before it
# reads as a conservation fault rather than rounding.
ENERGY_TOLERANCE = 0.05

UNKNOWN_SOURCE = "unknown"

# Fields that identify or label a claim rather than measure anything. They are
# not quantities, so they are not adjudicated and never explained - reporting
# that "watch beat app on the date field" is noise that buries the one line
# the athlete actually wanted to read.
# Provenance describes where a value came FROM; it is not a competing claim
# about the world, so it never resolves by the precedence ladder (#35/#51).
# Left in, `origin` and `path` were being reported as contested fields whose
# sources "disagreed" - which is true and meaningless: of course two chains
# differ, that is what makes them two chains.
# Fields that describe WHERE A CLAIM CAME FROM rather than what it says. They
# travel with their claim and are never adjudicated field-wise: merging them
# separately lets a canonical row take its value from one source and its
# provenance from another, which produces a row whose every provenance
# statement is false for the number it holds. `derived_from` and `derived_op`
# are here for that reason (#170) - an observed value wearing a derived row's
# lineage is precisely the laundering this layer exists to prevent, and the
# engine manufacturing it is worse than an athlete doing so.
NON_QUANTITY_FIELDS = {"date", "source", "origin", "path", "origin_evidence",
                       "derived_from", "derived_op"}


def claim_id(dataset: str, rec: dict, ordinal: int = 0) -> str:
    """A stable reference to one claim, used as a JTMS justification node.

    Sessions need the ordinal: an athlete can legitimately log two runs from
    the same source on the same day, and those are two claims, not one.
    """
    source = rec.get("source") or UNKNOWN_SOURCE
    base = f"{dataset}:{rec.get('date')}:{source}"
    return f"{base}:{ordinal}" if dataset == "sessions" else base


def _rank(source: object, order: tuple[str, ...]) -> tuple[int, str]:
    """Position of a source in a precedence ladder; unknown sources sort last.

    The source name is the tiebreak so two equally-unranked sources always
    resolve the same way - determinism outranks cleverness here.
    """
    name = str(source) if source else UNKNOWN_SOURCE
    return (order.index(name) if name in order else len(order), name)


def _ladder(field: str, precedence: dict[str, tuple[str, ...]],
            default: tuple[str, ...]) -> tuple[str, ...]:
    return precedence.get(field) or default


def _numeric(v: object) -> bool:
    # ONE definition, in `schema` (see `is_number`). This was three
    # byte-identical copies of a predicate that decides whether a value
    # reaches a gate.
    return is_number(v)


def _disagrees(a: object, b: object) -> bool:
    """Do two claims differ by more than tolerance? Non-numerics: differ at all."""
    if _numeric(a) and _numeric(b):
        if a == b:
            return False
        scale = max(abs(float(a)), abs(float(b))) or 1.0
        return abs(float(a) - float(b)) / scale > DISAGREEMENT_TOLERANCE
    return a != b


def _merge_fields(dataset: str, claims: list[tuple[str, dict]],
                  precedence: dict[str, tuple[str, ...]],
                  default: tuple[str, ...]) -> tuple[dict, list[dict], list[dict]]:
    """Field-wise precedence merge of claims that describe the same thing.

    Returns (canonical, justifications, explanations). A field with exactly
    one non-null witness is taken verbatim and explains nothing - the common
    case must stay silent, or the explanations become noise nobody reads.
    """
    canonical: dict = {}
    justifications: list[dict] = []
    explanations: list[dict] = []

    # Identity and provenance, set once rather than adjudicated. A merged row
    # names every source behind it, so a canonical value is never mistaken for
    # a single device's word.
    if "date" in KEYS[dataset]:
        canonical["date"] = claims[0][1].get("date")
    if "source" in KEYS[dataset]:
        contributors = sorted({str(rec.get("source") or UNKNOWN_SOURCE)
                               for _, rec in claims})
        canonical["source"] = "+".join(contributors)
    # `source` above lists the CHANNELS a value arrived by, and the `+` reads
    # as a union of independent sources - which is precisely the error (#51).
    # These say what it actually was: how many distinct instruments observed
    # it, and how much the journey could have changed it.
    if "origin" in KEYS[dataset]:
        recs = [rec for _, rec in claims]
        origins = sorted(distinct_origins(recs))
        canonical["origin"] = origins[0] if len(origins) == 1 else (
            "+".join(origins) if origins else None)
        # A merged row has as many paths as it had claims, so there is no
        # single one to record. The full set lives in `provenance.chain`;
        # putting one of them here would assert a journey this value did not
        # solely take.
        single = recs[0] if len(recs) == 1 else None
        canonical["path"] = single.get("path") if single else None
        canonical["origin_evidence"] = (single.get("origin_evidence")
                                        if single else None)
        # Same rule as `path`, for the same reason (#170). One claim keeps its
        # lineage; a merged row has none, because the value it ended up
        # holding was not solely computed from any one claim's inputs. A
        # merged row that kept one contributor's lineage would state a false
        # basis for a number that contributor did not supply.
        canonical["derived_from"] = single.get("derived_from") if single else None
        canonical["derived_op"] = single.get("derived_op") if single else None
        canonical["_provenance"] = {
            "independent_sources": independent_witnesses(recs),
            # Trust is bounded by the WEAKEST hop, not by the origin: a
            # device-measured weight that passed through a vendor which
            # rounds or re-derives is no longer device-measured (#51).
            # max over this order, not min: the ceiling is the LEAST
            # trustworthy hop any contributing claim passed through.
            "trust": max((trust_ceiling(r) for r in recs),
                         key=TRUST_ORDER.index),
            "chain": "; ".join(sorted({describe(r) for r in recs})),
        }

    # WHICH SOURCE SUPPLIED WHICH FIELD (#325), on a merged row only.
    #
    # THE CHANNEL, NOT THE INSTRUMENT, and the repo's own #35/#51 distinction
    # makes that worth saying out loud: `source` is the feed a value arrived
    # by, `origin` is the device that observed it. A watch relayed through a
    # platform has one origin and reaches the record under whichever source
    # the relay was recorded as. The issue asks for instruments and proposes a
    # map of sources; this is the map it proposes, named for what it holds.
    #
    # `explanations` looks like the answer and is not: it records the winner of
    # a CONTEST, and complementary instruments never contest. A watch supplies
    # heart rate, a console supplies distance, each field has ONE witness, and
    # a field with one witness "is taken verbatim and explains nothing" -
    # deliberately, or the explanations become noise nobody reads. So the case
    # this is for was exactly the case that stayed silent, and the merged row's
    # single `source` was true of half its values and false of the rest.
    #
    # Filled below as each field's winner is chosen, so it cannot drift from
    # what the row actually took.
    field_sources: dict[str, str] = {}
    # AND THE INSTRUMENT, which is what #325's title actually asks and what
    # `field_sources` cannot answer. `source` is the FEED a value arrived by;
    # `origin` is the device that observed it, and the two come apart on the
    # case the issue narrates - a hand-merged console row carrying the watch's
    # heart rate forward has `source: matrix-console` for a number a Polar
    # measured. Attributing that number to the console is true of the channel
    # and false of the instrument, and a consumer rendering "HR 142 (matrix
    # console)" is stating something no device ever said.
    #
    # A SEPARATE MAP RATHER THAN A REPLACEMENT. Both questions are real and a
    # consumer needs different ones at different times: which feed to re-pull
    # from, and which device to trust or retire. Most records answer only the
    # first - `origin` is optional and 57% of the corpus's daily rows carry
    # none - so folding them would make the answer disappear whenever the
    # weaker field is absent.
    field_origins: dict[str, str] = {}

    for field in KEYS[dataset]:
        if field in NON_QUANTITY_FIELDS:
            continue
        witnesses = [(cid, rec) for cid, rec in claims if rec.get(field) is not None]
        if not witnesses:
            canonical[field] = None
            continue
        ladder = _ladder(field, precedence, default)
        # AFTER the source ladder and BEFORE recency (#140).
        #
        # After, because precedence is the athlete's configured judgement and
        # this is not entitled to overrule it: two different sources still
        # resolve the way they were told to.
        #
        # Before recency, because the failure this fixes is a later claim
        # carrying a MORE restated number - a weight logged from memory as
        # `source: scale` beside the scale's own reading. Ranking recency
        # first would let the recollection win for being newer, which is the
        # whole finding.
        #
        # AND ONLY WHEN EVERY CLAIM IN THE CONTEST SAYS. Unstated is not
        # absent: defaulting silence to the worst rank made a line that said
        # nothing lose to a line that said `file_export`, so a re-export
        # carrying no capture lost to the previous morning's annotated one -
        # #70's error, reintroduced by the fix for #140. A record part-way
        # through adopting `capture` is the normal case, and there it decides
        # nothing and recency behaves exactly as before.
        stated = all(states_capture(rec) for _, rec in witnesses)
        witnesses.sort(key=lambda w: (_rank(w[1].get("source"), ladder),
                                      restatements(w[1]) if stated else 0,
                                      *_recency(w[1])))
        winner_id, winner = witnesses[0]
        canonical[field] = winner[field]
        field_sources[field] = str(winner.get("source") or UNKNOWN_SOURCE)
        # SILENCE IS NOT AN ENTRY, enforced here as well as in the pruner,
        # and the two are NOT equivalent - which is why this one needs its own
        # comment and its own test. The pruner's bucket-skip stops an
        # origin-less claim being re-attributed to; this stops a field WON by
        # an origin-less claim from being attributed at all. Without it, a
        # value the manual line supplied gets handed to whichever single
        # instrument happens to corroborate it - measured, and it attributed
        # `type` to a watch, a device "observing" the word "row".
        if winner.get("origin"):
            field_origins[field] = str(winner["origin"])
        # `witnesses` counts INDEPENDENT ORIGINS, not rows (#35/#51). Five
        # rows carrying one watch's reading through five platforms are one
        # witness, and reporting five is the false confidence this exists to
        # prevent - independent instruments corroborate, a sync pipeline does
        # not.
        witness_recs = [rec for _, rec in witnesses]
        justifications.append({
            "field": field,
            "claim_id": winner_id,
            "source": winner.get("source") or UNKNOWN_SOURCE,
            "tier": "observed",
            "quantity_class": QUANTITY_CLASS.get(dataset, "measured_flow"),
            "witnesses": independent_witnesses(witness_recs),
            "origin": winner.get("origin"),
            "trust": trust_ceiling(winner),
        })
        if len(witnesses) > 1:
            loser_id, loser = witnesses[1]
            # EVERY discarded claim, not only the runner-up (#73). A resolved
            # value had no way to say what it beat, so an unattributed row
            # losing a contest it should have won left no trace anywhere -
            # the only way either live instance was found was reading the raw
            # JSONL by hand.
            discarded = "; ".join(
                f"{rec.get('source') or UNKNOWN_SOURCE}={rec[field]}"
                for _, rec in witnesses[1:])
            explanations.append({
                "date": winner.get("date"),
                "dataset": dataset,
                "field": field,
                "chosen_source": winner.get("source") or UNKNOWN_SOURCE,
                "chosen_value": winner[field],
                "over_source": loser.get("source") or UNKNOWN_SOURCE,
                "over_value": loser[field],
                "witnesses": independent_witnesses(witness_recs),
                "reason": _why(winner, loser, ladder),
                # Which axis actually decided. `_contradictions` needs it: a
                # capture-decided contest shares a source and is NOT the
                # correction mechanism, so the same-source skip would
                # swallow a device reading and a recollection disagreeing by
                # any amount at all.
                "by_capture": _by_capture(winner, loser),
                # EVERY DISCARD, not only the runner-up - the same widening
                # `discarded` got one line above, and the comment beside
                # `unattributed_loser` below already names this exact defect:
                # "`disagreed` compares the winner with the runner-up only, so
                # a third unattributed claim differing wildly went unnoticed".
                # It was fixed there and not here, in the same dict.
                #
                # The consequence reaches a reader: `_contradictions` gates the
                # `source_disagreement` tripwire on this flag, and the CLI
                # marks a contested line with `!` only when it is set. So a
                # scale saying 70.0, an app saying 70.0 and a watch saying 74.5
                # produced no mark and no tripwire, because the runner-up
                # happened to agree.
                #
                # WHICH ONE IT NAMES stays the runner-up: `over_source` and
                # `over_value` describe the contest the ladder actually
                # decided, and `discarded` beside them lists the rest. This
                # flag answers "is there a disagreement here", which is a
                # question about all of them.
                "disagreed": any(_disagrees(winner[field], rec[field])
                                 for _, rec in witnesses[1:]),
                # Same origin means these are one measurement seen at two
                # points on one pipe. The spread then measures PIPELINE
                # FIDELITY, not truth - worth reporting, never worth counting
                # as validation (#51).
                #
                # `same_witness` rather than `shares_origin` (#211), because
                # `witnesses` above already counts by channel where no
                # instrument is named. Keying the label on instrument alone
                # emitted one witness beside the words "independent
                # observations" for the same pair: two fields, one question,
                # two answers, on a row whose whole job is to say how well
                # evidenced a value is.
                "independent": not same_witness(winner, loser),
                "compares": ("pipeline fidelity" if same_witness(winner, loser)
                             else "independent observations"),
                "discarded": discarded,
                # The signature of #73: a row with no source lost to a ranked
                # one. An unattributed row is USUALLY a writer omission rather
                # than genuinely doubtful provenance, and the sources that go
                # unattributed are the first-hand ones - a hand-entered
                # figure, a chat-stated number, a note typed on a phone -
                # which are exactly the rows the ladder ranks ABOVE vendor
                # channels. So the omission inverts the ladder precisely where
                # it matters most.
                # Tested against the WINNER, over every discard, and on
                # exact inequality rather than the 10% disagreement
                # tolerance. Both matter: `disagreed` compares the winner
                # with the runner-up only, so a third unattributed claim
                # differing wildly went unnoticed; and 10% of a day's burn is
                # ~300 kcal, which is enough to flip a surplus into a deficit
                # while counting as agreement.
                "unattributed_loser": any(
                    not rec.get("source") and rec[field] != winner[field]
                    for _, rec in witnesses[1:]),
            })
    # MORE THAN ONE SOURCE, not more than one row, and counting rows was
    # wrong. Two claims from the SAME source - an informal re-export
    # correcting an earlier line, which `_recency` calls the commonest case -
    # are one writer, and the canonical `source` says so by staying a bare
    # name with no `+`. A map there is ceremony on exactly the rows the issue
    # asks us not to burden, and worse, a consumer using its presence as the
    # merge signal would have been misled in both directions.
    if isinstance(canonical.get("_provenance"), dict) and len(
            {str(rec.get("source") or UNKNOWN_SOURCE)
             for _, rec in claims}) > 1:
        canonical["_provenance"]["field_sources"] = dict(field_sources)
        canonical["_provenance"]["field_origins"] = dict(field_origins)

    return canonical, justifications, explanations


def _recency(rec: dict) -> tuple[int, float]:
    """Sort key fragment putting the LATEST-WRITTEN claim first (#70).

    Precedence decides between DIFFERENT sources. It cannot decide between two
    claims from the SAME source - they tie - and a stable sort then left the
    first line of the file winning forever. Which meant the correction path
    was dead for its commonest shape: a correction almost always comes from
    the same source as the thing it corrects, because a vendor re-exports, an
    importer re-runs, or a log is completed later.

    The live case: a food log exported at breakfast said 1,354 kcal; the same
    log exported the next morning, after dinner was entered, said 3,091. Both
    claims are in the record correctly, the later one carrying a later
    `recorded_at` - and the record kept asserting 1,354, a 1,700 kcal error
    feeding straight into deficit arithmetic.

    An unstamped claim sorts LAST, so any stamped claim beats it, and among
    unstamped claims the stable sort preserves file order - which is exactly
    what a legacy record does today.

    NARROWED BY #140, and only where the record asked for it: when every
    claim in the contest STATES a capture, the one closest to the instrument
    is preferred before this runs. So an informal same-source correction -
    retyping a value with no `supersedes` - no longer wins by being newer if
    it is also more restated than what it corrects. That is the point (a
    weight logged from memory beside the scale's own reading), and the
    deliberate correction path is `supersedes`, which retires its target at
    load. Where any claim is silent about capture, nothing changes here.
    """
    when = stamp_instant(rec.get("recorded_at"))
    return (1, 0.0) if when is None else (0, -when.timestamp())


def _by_capture(winner: dict, loser: dict) -> bool:
    """Did capture decide this, rather than precedence or recency?"""
    return (states_capture(winner) and states_capture(loser)
            and restatements(winner) < restatements(loser))


def _why(winner: dict, loser: dict, ladder: tuple[str, ...]) -> str:
    w = str(winner.get("source") or UNKNOWN_SOURCE)
    ll = str(loser.get("source") or UNKNOWN_SOURCE)
    # Same source on both sides means precedence decided nothing - recency
    # did. Saying "mfp-export outranks mfp-export" is false, and it is false
    # in the audit trail, which is the one place the record explains itself.
    if w == ll:
        # ...unless capture did, which is the case precedence cannot see. The
        # audit trail has to name the reason it actually used, or a resolution
        # nobody can explain is one nobody can dispute.
        #
        # DIRECTIONAL. Testing only that the ranks differ read correctly when
        # the sort had already put the closer claim first, and stated the
        # exact reverse when anything else decided - a false sentence in the
        # one place the record explains itself.
        if _by_capture(winner, loser):
            return (f"same source; {capture_of(winner)} is closer to the "
                    f"instrument than {capture_of(loser)}")
        return f"same source; the later-written {w} claim supersedes the earlier"
    if w in ladder and ll not in ladder:
        return f"{w} is ranked for this quantity, {ll} is not"
    if w in ladder and ll in ladder:
        return f"{w} outranks {ll} for this quantity"
    return f"neither source is ranked; {w} sorts first"


def _carry_meta(canonical: dict, claims: list[tuple[str, dict]],
                dataset: str | None = None) -> dict:
    """Keep the highest schema generation seen, so a merged row is not
    mistaken for an older-shaped one - and keep the identity triple coherent."""
    gens = [c.get("_gen") for _, c in claims if isinstance(c.get("_gen"), int)]
    if gens:
        canonical["_gen"] = max(gens)
    if dataset is not None:
        _keep_identity_together(dataset, canonical, claims)
    _prune_field_sources(canonical, claims)
    return canonical


def _prune_field_sources(canonical: dict, claims: list[tuple[str, dict]]) -> None:
    """Drop any attribution the finished row no longer supports (#325).

    The map is filled as each field's winner is chosen, which is right for a
    quantity and NOT ENOUGH on its own: `_keep_identity_together` runs
    afterwards and takes the identity triple from one claim in file order
    rather than from the ladder winner. So the map could name `polar` for an
    `activity_id` the console supplied, and could name a source for `track`
    on a row whose `track` ended up null - naming a field the row does not
    hold, which is the one thing this must never do.

    Checked against the FINISHED row rather than trusted from the moment of
    the merge. An attribution that cannot be shown true is dropped: silence is
    a worse answer than a name, and a wrong name is worse than both.
    """
    meta = canonical.get("_provenance")
    if not isinstance(meta, dict):
        return
    for key, attr in (("field_sources", "source"), ("field_origins", "origin")):
        named = meta.get(key)
        if not isinstance(named, dict):
            continue
        by_name: dict[str, list[dict]] = {}
        for _, rec in claims:
            if attr == "origin" and not rec.get("origin"):
                # An unstated origin is not a name. `source` defaults to
                # UNKNOWN_SOURCE because a claim always arrived SOMEHOW;
                # `origin` is optional and silence about the instrument must
                # not become a bucket that can be attributed to.
                continue
            by_name.setdefault(str(rec.get(attr) or UNKNOWN_SOURCE),
                               []).append(rec)
        meta[key] = _substantiated(canonical, named, by_name)


def _substantiated(canonical: dict, named: dict[str, str],
                   by_name: dict[str, list[dict]]) -> dict[str, str]:
    """The attributions the finished row can still show true."""
    kept = {}
    for field, name in named.items():
        value = canonical.get(field)
        if value is None:
            continue                    # the row does not hold it after all
        if any(rec.get(field) == value for rec in by_name.get(name, ())):
            kept[field] = name
            continue
        # A later step took this from somewhere else. Re-attribute it if
        # exactly one claimant can account for the value, and say nothing if
        # more than one can - a coin toss between two claims that agree is not
        # attribution.
        #
        # THAT RULE IS DELIBERATELY NOT APPLIED ABOVE, and I tried to "fix"
        # that before measuring what it would cost. Where the ladder winner
        # DOES hold the value, several witnesses agreeing on it is not a coin
        # toss: the ladder decided, and `explanations.chosen_source` and
        # `justifications` name the same winner for the same field. Dropping
        # the attribution there would make this map disagree with the other
        # two provenance surfaces about who won, to express something they
        # already express better - corroboration is `independent_sources`, a
        # contest is `explanations`. This map answers which claimant supplied
        # the value the row took, and that question has an answer here.
        owners = {who for who, recs in by_name.items()
                  if any(rec.get(field) == value for rec in recs)}
        if len(owners) == 1:
            kept[field] = owners.pop()
        # NO CONTROL FOR THE `> 1` CASE, and this note is here because review
        # found it unwitnessed and I could not fix it. Mutating the condition
        # to take an arbitrary owner passes the whole suite. Reaching it needs
        # a value that MOVED after the merge - in practice the session
        # identity triple - held by two claimants of one canonical row, and
        # sessions bucket BY `activity_id`, so a second claimant for the moved
        # identity splits into a separate row instead of contesting it. Every
        # fixture I built either merged with one claimant or did not merge.
        #
        # Left standing rather than deleted: it predates this change, it is
        # the conservative direction (say nothing rather than guess), and a
        # branch I cannot reach is also a branch I cannot show is dead. What I
        # will not do is claim it is tested.
    return kept


# The external identity of a session is a TRIPLE, and its parts are only
# meaningful together (#43).
IDENTITY_TRIPLE = ("activity_id", "activity_source", "track")


def _keep_identity_together(dataset: str, canonical: dict,
                            claims: list[tuple[str, dict]]) -> None:
    """Take the identity triple from ONE claim, not field by field.

    Per-field precedence is right for quantities - each resolves on its own
    merits. It is wrong for an identity: resolving `activity_id` and
    `activity_source` independently can pair one platform's id with another
    platform's name for who assigned it, which asserts a provenance neither
    source ever claimed. That is the #35 error made by the resolver rather
    than by a connector.

    Two platforms recording one activity genuinely have two ids. A canonical
    row can hold one, so it holds a COHERENT one - and both raw ids survive
    untouched in `claims`, which is where the full trail lives.
    """
    if dataset != "sessions":
        return
    owner = next((rec for _, rec in claims if rec.get("activity_id")), None)
    if owner is None:
        return
    for field in IDENTITY_TRIPLE:
        if field in KEYS[dataset]:
            canonical[field] = owner.get(field)


# --- session activity identity ------------------------------------------------

def _interval(rec: dict, start: datetime | None = None
              ) -> tuple[datetime, datetime] | None:
    """The (start, end) a session occupies, or None without a start_time.

    `start` lets a caller pass an already-frame-aligned instant (see
    `_same_activity`), so the two intervals being compared are read in the
    same frame rather than each parsing itself independently.
    """
    if start is None:
        if not (st := rec.get("start_time")):
            return None
        if (start := parse_time(st)) is None:
            return None
    seconds = rec.get("duration_s") if _numeric(rec.get("duration_s")) else 0
    return start, start + timedelta(seconds=float(seconds or 0))


def _ratio(a: object, b: object) -> float | None:
    if not (_numeric(a) and _numeric(b)) or not float(b):
        return None
    return float(a) / float(b)


def _frames_differ(a: dict, b: dict) -> bool:
    """Do these two claims carry timestamps that cannot be compared? (#38)

    True only when BOTH have a start_time and one is naive while the other
    carries an offset - the mixture that used to raise, and that no amount of
    guessing can turn into two honest instants.
    """
    ta, tb = parse_time(a.get("start_time")), parse_time(b.get("start_time"))
    return ta is not None and tb is not None and is_aware(ta) != is_aware(tb)


def _same_activity(a: dict, b: dict) -> str:
    """MATCH | POSSIBLE | DISTINCT for two session claims on one date.

    Three outcomes rather than two, following the Fellegi-Sunter shape of
    record linkage: link, POSSIBLE link, non-link, with the uncertain middle
    held back rather than resolved. A possible match never merges - it is
    reported and both claims survive.

    Timestamps are the strong test: two platforms recording one run describe
    overlapping intervals, and nothing else does.

    Shape - same type, similar duration, similar distance - is the weak test,
    and the correction this function exists for (issue #14) is that shape is
    NOT evidence of identity. It was being used as a proxy for "same activity"
    when for repeated activities it is a proxy for ROUTINE: a dog walked three
    times a day, a commute each way, sets of the same length. Anyone with a
    habit generates near-identical shapes BY DESIGN, and merging them silently
    deleted their data.

    So a shape match now also requires DISJOINT SOURCES. A genuine
    cross-platform duplicate has a signature the shape does not carry - two
    different systems each claiming one physical event. Two claims from the
    same source with the same shape are far more likely to be two real events,
    and an identical re-emission from one connector is a connector bug that
    exact-duplicate detection (G26) already covers.
    """
    # #38: the record holds naive and offset-aware timestamps side by side,
    # and comparing them directly RAISED - taking the whole build down rather
    # than degrading. Two timestamps that cannot be compared are a resolution
    # outcome to report, never an exception, and never a guessed instant: the
    # strong test is simply unavailable, so the weaker shape test decides and
    # the caller says why.
    start_a, start_b, ok = comparable(parse_time(a.get("start_time")),
                                      parse_time(b.get("start_time")))
    ia, ib = ((_interval(a, start_a), _interval(b, start_b)) if ok
              else (None, None))
    if ia and ib:
        if ia[0] < ib[1] and ib[0] < ia[1]:
            return MATCH
        gap = min(abs((ia[0] - ib[1]).total_seconds()),
                  abs((ib[0] - ia[1]).total_seconds()))
        return (POSSIBLE if gap <= 600 and a.get("type") == b.get("type")
                else DISTINCT)
    if a.get("type") != b.get("type"):
        return DISTINCT

    dur = _ratio(a.get("duration_s"), b.get("duration_s"))
    dist = _ratio(a.get("distance_km"), b.get("distance_km"))
    if dur is None and dist is None:
        return DISTINCT

    def within(r: float | None, band: tuple[float, float], slack: float) -> bool:
        return r is None or band[0] - slack <= r <= band[1] + slack

    alike = within(dur, DURATION_RATIO, 0.0) and within(dist, DISTANCE_RATIO, 0.0)
    near = (not alike
            and within(dur, DURATION_RATIO, NEAR_MISS_SLACK)
            and within(dist, DISTANCE_RATIO, NEAR_MISS_SLACK))
    if not alike:
        return POSSIBLE if near else DISTINCT
    # Alike in shape. Only a second, independent witness makes that identity.
    same_source = (a.get("source") or UNKNOWN_SOURCE) == (b.get("source")
                                                          or UNKNOWN_SOURCE)
    return POSSIBLE if same_source else MATCH


def _richness(rec: dict) -> int:
    return sum(1 for v in rec.values() if v is not None)


def _routine_types(claims: list[tuple[str, dict]]) -> set[str]:
    """Session types whose claims look like a habit rather than a duplicate set.

    If more than ROUTINE_THRESHOLD timestamp-less claims of one type land on
    one date, shape-matching them is meaningless: their similarity is what
    having a routine looks like. No shape merge is attempted for those types.
    """
    counts: dict[str, int] = {}
    for _, rec in claims:
        if _interval(rec) is None:
            key = str(rec.get("type"))
            counts[key] = counts.get(key, 0) + 1
    return {t for t, n in counts.items() if n > ROUTINE_THRESHOLD}


def _cluster_sessions(claims: list[tuple[str, dict]]) -> tuple[list[list[tuple[str, dict]]],
                                                               list[dict]]:
    """Group one date's session claims into physical activities.

    A merge that removes volume from the record is exactly the class of event
    the tripwires exist for, so every shape-only merge is REPORTED. Before
    issue #14 a merge was invisible outside the `claims` table, which is how a
    day of four walks came to read as one.
    """
    clusters: list[list[tuple[str, dict]]] = []
    notes: list[dict] = []
    routine = _routine_types(claims)
    flagged_routine: set[str] = set()

    for cid, rec in claims:
        kind = str(rec.get("type"))
        if kind in routine:
            clusters.append([(cid, rec)])
            if kind not in flagged_routine:
                flagged_routine.add(kind)
                notes.append({
                    "date": rec.get("date"),
                    "kind": "repeated_activity_kept",
                    "detail": (f"several similar {kind} sessions on one date with "
                               "no start_time: treated as a routine and kept "
                               "separate, not merged. Record start_time to "
                               "resolve them positively"),
                    "severity": "review",
                })
            continue

        placed = False
        for cluster in clusters:
            head = cluster[0][1]
            verdict = _same_activity(head, rec)
            if verdict == MATCH and shares_origin(head, rec):
                # One reading seen at two points on one pipe. It still merges
                # - it IS one activity - but the record must not let that
                # read as two platforms agreeing, which is the whole of #35.
                notes.append({
                    "date": rec.get("date"),
                    "kind": "relayed_not_corroborated",
                    "detail": (
                        f"{rec.get('source') or UNKNOWN_SOURCE} and "
                        f"{head.get('source') or UNKNOWN_SOURCE} both carry "
                        f"the same {rec.get('origin')} recording of this "
                        f"{kind}. Merged as one activity, and counted as ONE "
                        "observation - a sync pipeline is not a second witness"),
                    "severity": "info",
                })
            if verdict != DISTINCT and _frames_differ(head, rec):
                # #38: both rows HAVE a timestamp, and it could not be used.
                # Without this the pair looks like an ordinary shape-only
                # merge - "no start_time" - which is not what happened and
                # would send someone off to record a field they already have.
                notes.append({
                    "date": rec.get("date"),
                    "kind": "incomparable_timestamps",
                    "detail": (
                        f"{rec.get('source') or UNKNOWN_SOURCE} and "
                        f"{head.get('source') or UNKNOWN_SOURCE} logged {kind} "
                        "sessions whose start_time shapes do not match (one "
                        "naive, one offset-aware), so the timestamps could not "
                        "be compared and shape decided it. Write offset-"
                        "bearing start_time on both to settle it by instant"),
                    "severity": "review",
                })
            if verdict == MATCH:
                cluster.append((cid, rec))
                placed = True
                if _interval(head) is None or _interval(rec) is None:
                    notes.append({
                        "date": rec.get("date"),
                        "kind": "shape_only_merge",
                        "detail": (
                            f"{rec.get('source') or UNKNOWN_SOURCE} and "
                            f"{head.get('source') or UNKNOWN_SOURCE} logged "
                            f"{kind} sessions of near-identical shape with no "
                            "start_time; treated as ONE activity. If they were "
                            "two, add start_time and rebuild"),
                        "severity": "review",
                    })
                break
            if verdict == POSSIBLE:
                notes.append({
                    "date": rec.get("date"),
                    "kind": "near_miss_duplicate",
                    "detail": (f"{rec.get('source') or UNKNOWN_SOURCE} and "
                               f"{head.get('source') or UNKNOWN_SOURCE} "
                               f"logged similar {kind} sessions that did not "
                               "match closely enough to merge"),
                    "severity": "review",
                })
        if not placed:
            clusters.append([(cid, rec)])
    return clusters, notes


# --- the entry point ----------------------------------------------------------

def resolve(datasets: dict[str, list[dict]],
            precedence: dict[str, tuple[str, ...]] | None = None,
            source_order: tuple[str, ...] = ()) -> dict:
    """Adjudicate every claim into canonical rows.

    Returns a dict with the canonical datasets plus the audit trail:
    `claims` (every raw claim with its id), `explanations` (which source won
    a contested field and why - G29), `justifications` (the JTMS links) and
    `tripwires` (conservation faults, flagged never fixed).
    """
    precedence = precedence or {}
    canonical: dict[str, list[dict]] = {}
    claims_out: list[dict] = []
    explanations: list[dict] = []
    justifications: list[dict] = []
    tripwires: list[dict] = []
    provenance: list[dict] = []

    for dataset in RESOLVED_DATASETS:
        rows = datasets.get(dataset) or []
        by_date: dict[str, list[tuple[str, dict]]] = {}
        counters: dict[str, int] = {}
        for rec in rows:
            if not rec.get("date"):
                continue
            key = f"{dataset}:{rec['date']}:{rec.get('source') or UNKNOWN_SOURCE}"
            ordinal = counters.get(key, 0)
            counters[key] = ordinal + 1
            cid = claim_id(dataset, rec, ordinal)
            by_date.setdefault(rec["date"], []).append((cid, rec))
            claims_out.append({
                "claim_id": cid, "dataset": dataset, "date": rec["date"],
                "source": rec.get("source") or UNKNOWN_SOURCE,
                "kind": rec.get("kind") or rec.get("type"),
                "retracted": 0,
            })

        resolved: list[dict] = []
        for when in sorted(by_date):
            day = by_date[when]
            groups = [day]
            if dataset == "sessions":
                groups, near = _cluster_sessions(day)
                tripwires += near
            elif dataset == "measurements":
                # Each measurement KIND is its own quantity; a waist reading
                # and a DEXA body-fat read on one day are not competing claims.
                by_kind: dict[str, list[tuple[str, dict]]] = {}
                for cid, rec in day:
                    by_kind.setdefault(str(rec.get("kind")), []).append((cid, rec))
                groups = [by_kind[k] for k in sorted(by_kind)]

            for group in groups:
                merged, just, expl = _merge_fields(dataset, group, precedence,
                                                   source_order)
                merged = _carry_meta(merged, group, dataset)
                if (chain := merged.pop("_provenance", None)) is not None:
                    provenance.append({"dataset": dataset, "date": when,
                                       "origin": merged.get("origin"), **chain})
                resolved.append(merged)
                explanations += expl
                for j in just:
                    justifications.append({**j, "dataset": dataset, "date": when})
                if len(group) > 1:
                    for cid, _ in group[1:]:
                        for c in claims_out:
                            if c["claim_id"] == cid:
                                c["merged_into"] = group[0][0]
        canonical[dataset] = ([canonical_daily(r) for r in resolved]
                              if dataset == "daily" else resolved)

    # Policy and model-tier datasets pass through untouched: they are not
    # competing measurements of one quantity.
    for name in KEYS:
        canonical.setdefault(name, list(datasets.get(name) or []))

    tripwires += _unattributed_losses(explanations)
    tripwires += _unread_retired_values(datasets)
    tripwires += _conservation(canonical["daily"], canonical["sessions"])
    tripwires += [t for t in _contradictions(explanations)]
    # AFTER resolution, because a regime empties what resolution produced: the
    # claims still resolve, and then the days a declared regime covers stop
    # standing as values.
    tripwires += apply_regimes(canonical, datasets.get("regimes") or [])
    # A value standing on an input the record has retracted (#170). Detected
    # from DECLARED lineage, reported rather than recomputed: `derived_op` is
    # free text and non-executable, so the engine cannot produce a corrected
    # number and will not invent one.
    tripwires += derivation_cycles(datasets)
    # The ledger is computed once and read twice, and EMISSION ENTRIES ARE
    # KEPT OUT of what `stale_derivations` receives. They were left in at
    # first, on the reasoning that nothing derives from an emission so the
    # widening could only ever be inert. It is not inert: emission ids come
    # from the row grammar and carry an ORDINAL, `_lineage_to_claim_id` strips
    # a trailing ordinal before it compares, and the two together made a
    # lineage naming the second emission of a day match the first one's
    # ledger id. That is a false stale finding about a row nobody restated,
    # and it reports an emission as restated, which this ledger's own rule
    # says never happens.
    ledger = retractions(datasets)
    tripwires += stale_derivations(
        datasets, {str(r["claim_id"]) for r in ledger
                   if r.get("claim_id") and r.get("kind") != "emission"})
    # And the same relation one rung up: not a value that moved, but something
    # the engine SAID on the strength of one (#134).
    tripwires += unsupported_assertions(ledger)
    # A restriction the engine cannot act on (#75). Not a correction problem
    # like the two above - a row that is complete to a reader and inert to the
    # machine, which is worse than a missing value because a missing value is
    # at least legible as missing.
    tripwires += unenforceable_restrictions(datasets)
    # ADVISORY, and last: a constant run is a question about how a number was
    # acquired, never a fault in the arithmetic above it. AFTER apply_regimes
    # deliberately: a declared regime has already emptied its interval, so the
    # detector cannot re-flag a restatement the athlete has already named.
    tripwires += restatement_runs(canonical)
    tripwires.sort(key=lambda t: (t["date"] or "", t["kind"], t["detail"]))
    explanations.sort(key=lambda e: (e["date"] or "", e["dataset"], e["field"]))
    justifications.sort(key=lambda j: (j["date"] or "", j["dataset"], j["field"]))
    claims_out.sort(key=lambda c: (c["date"], c["dataset"], c["claim_id"]))
    provenance.sort(key=lambda r: (r["date"] or "", r["dataset"],
                                   str(r.get("origin") or "")))

    return {"canonical": canonical, "claims": claims_out,
            "explanations": explanations, "justifications": justifications,
            "tripwires": tripwires, "provenance": provenance}


def canonical_daily(rec: dict) -> dict:
    """Read a daily row with the retired `hip_pain` mapped forward and the
    site normalised to its registry slug.

    Old lines said `hip_pain: 3`; the generalized shape says `pain: 3` at
    `pain_site: "hip"`. Rather than rewrite history - which the append-only
    rule forbids outright - the engine reads the old field as what it always
    meant. A line that carries BOTH keeps its explicit `pain`, because a line
    written under the new shape knows better than this mapping does.

    Legacy lines get no `pain_side`, and none is invented: the old field never
    recorded which hip, and guessing a side would manufacture a fact.
    """
    from .anatomy import resolve

    out = rec
    if out.get("pain") is None and out.get("hip_pain") is not None:
        out = {**out, "pain": out["hip_pain"],
               "pain_site": out.get("pain_site") or "hip"}
    # Normalise whatever spelling was written onto the canonical slug, so
    # "IT band" and "itb" group with "knee" downstream.
    if (site := out.get("pain_site")) and (slug := resolve(site)) and slug != site:
        out = {**out, "pain_site": slug}
    return out


def _ref_to_claim_id(dataset: str, ref: str) -> str | None:
    """Translate a `supersedes` reference into the claim id it retires."""
    if "/" not in ref:
        return None            # identity-keyed policy line, not an observation
    when, _, source = ref.partition("/")
    return f"{dataset}:{when}:{source or UNKNOWN_SOURCE}"


# THE JUSTIFICATION LINK, AND EVERY SPELLING OF IT (#134).
#
# The complaint #134 files is that the link "applies to one dataset only".
# That is not what the record holds. Three fields already say "the claims
# this rests on", under three names, and they had two read paths between
# them:
#
#   `inferences.depends_on`   cascaded here, and only here.
#   `derived_from`            on six lineage datasets, cascaded multi-hop by
#                             `stale_derivations` over every dataset that
#                             carries it - the generalisation already exists
#                             for values.
#   `emissions.basis_claims`  validated on write, stored in the read model,
#                             and read by NOTHING. The dataset's own comment
#                             says `basis_retracted` is "the next rung".
#
# So a fourth spelling is not what was missing. What was missing is the
# cascade over the third, which is the one that matters most: an assertion
# DELIVERED to a person is the only one of the three that somebody acted on.
#
# This map names the field each cascade reads. It is NOT a dispatch table the
# cascade walks: the two entries produce different ledger shapes and rest on
# different sets, so they stay two explicit loops rather than one generic one
# pretending they are the same operation.
#
# The control that goes with it lives in `test_justification.py`, and its
# limit is worth knowing: it proves each dataset named here is really read, by
# building a record and checking an entry appears, and it catches a KNOWN link
# name arriving on a dataset with no reader. It cannot catch a field with a
# name nobody has thought of yet.
JUSTIFICATION_LINK = {"inferences": "depends_on", "emissions": "basis_claims"}


def _dependencies(rec: dict, field: str) -> list[str]:
    """The claim ids a row declares it rests on.

    Tolerant of the two shapes the format admits: a JSON list, which is what
    the engine writes, and a whitespace or comma separated string, which is
    what a hand-edited line tends to carry.

    No default for `field`: a default here would be a spelling this function
    prefers, and the point of #134 is that it has no favourite among them.
    """
    raw = rec.get(field)
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [part.strip() for part in str(raw).replace(",", " ").split() if part.strip()]


def _undermined_by(deps: list[str], undermined: set[str]) -> list[str]:
    """Which of a row's declared bases have come down.

    THE ORDINAL IS DROPPED FIRST, and this is the whole of the finding. The
    engine publishes TWO spellings of one claim: `claim_id` appends an ordinal
    on `sessions`, because an athlete can log two runs from one source on one
    day, while `_ref_to_claim_id` - which is what builds the retracted set out
    of a `supersedes` reference - cannot know the ordinal and never emits one.
    So a consumer doing the obvious right thing, copying an id out of the
    engine's own `claims` table into `basis_claims`, wrote a justification
    that could never fall. It failed silently: no warning on write, no finding
    on read, and a shipped demo that dodged it by hand-writing the spelling no
    surface actually emits.

    `_lineage_to_claim_id` made this same reduction for `derived_from` and
    named the cost: dropping the ordinal means a basis naming the SECOND
    reading of a day is judged by whether that date and source were restated
    at all. That is a deliberate over-report on a dataset where the retracted
    set has no ordinal to compare against, and it is the right way round - the
    alternative is the silent miss above.
    """
    out = set()
    for dep in deps:
        if dep in undermined:
            out.add(dep)
            continue
        parts = dep.split(":")
        if len(parts) >= 4 and parts[-1].isdigit() and (
                ":".join(parts[:-1]) in undermined):
            out.add(dep)
    return sorted(out)


def retractions(datasets: dict[str, list[dict]]) -> list[dict]:
    """The JTMS ledger: what stopped being true, and what fell with it.

    A correction does not merely replace a number - it revokes the
    justification that number was holding up. Anything resting on it has to
    come down too, or the record keeps a belief whose evidence no longer
    exists ("stroller pace" surviving after the athlete says there was no
    child). This is the labeled-assumption-set + cascade-invalidate rule from
    JTMS (Doyle 1979), and deliberately nothing more: no full ATMS, no
    LLM-assigned confidence. Confidence is a property of tier and source.

    THE CASCADE RUNS TWICE, and the second hop is the point of #134. An
    inference that falls is a belief nobody necessarily saw. An EMISSION is
    something the engine told a person, on a named surface, under a named
    contract - the one artifact here that somebody may have acted on. It
    cascades off retracted claims AND off fallen inferences, because an
    assertion delivered on the strength of an inference that has since come
    down is in exactly the position this ledger exists to report.

    AN EMISSION IS NEVER RETRACTED BY THIS, and the wording is load-bearing.
    It is an event: the engine did say that, on that day, to that surface,
    and no later correction can make it not have happened - which is why
    `emissions` never retires. What the ledger records is that what it rested
    on was restated. The reader decides what that means, and #148 owns the
    harder question of whether the statement would still be made today.
    """
    from .identity import refs

    ledger: list[dict] = []
    retracted: set[str] = set()
    for dataset in RESOLVED_DATASETS:
        for rec in datasets.get(dataset) or []:
            if not (ref := rec.get("supersedes")):
                continue
            if (cid := _ref_to_claim_id(dataset, str(ref))) is None:
                continue
            retracted.add(cid)
            ledger.append({
                "date": rec.get("date"), "kind": "claim", "claim_id": cid,
                "retracted_by": claim_id(dataset, rec),
                "reason": rec.get("note") or "superseded by a correction",
                "cascaded_from": None,
            })

    # Cascade: an inference standing on a retracted claim falls with it.
    fallen_inferences: set[str] = set()
    link = JUSTIFICATION_LINK["inferences"]
    for rec in datasets.get("inferences") or []:
        for dep in _undermined_by(_dependencies(rec, link), retracted):
            cid = f"inference:{rec.get('date')}:{rec.get('model')}"
            fallen_inferences.add(cid)
            ledger.append({
                "date": rec.get("date"), "kind": "inference",
                "claim_id": cid,
                "retracted_by": dep,
                "reason": (f"rests on {dep}, which was retracted: "
                           f"{str(rec.get('statement') or '')[:80]}"),
                "cascaded_from": dep,
            })

    # Second hop: an assertion the engine DELIVERED, resting on something that
    # has come down. Identified by `refs`, the engine's own row grammar,
    # because two assertions on one day are two events and an identity built
    # from `date` alone could not name which of them fell.
    emissions = list(datasets.get("emissions") or [])
    undermined = retracted | fallen_inferences
    link = JUSTIFICATION_LINK["emissions"]
    for ref, rec in zip(refs("emissions", emissions), emissions):
        for dep in _undermined_by(_dependencies(rec, link), undermined):
            # WHICH WAY IT CAME DOWN, because the two are not the same event
            # and one wording for both would be false half the time: a claim
            # was RESTATED by a correction somebody wrote, an inference FELL
            # because its own justification went. Neither is the emission
            # being withdrawn.
            went = ("has since fallen" if dep in fallen_inferences
                    else "the record has since restated")
            ledger.append({
                "date": rec.get("date"), "kind": "emission", "claim_id": ref,
                "retracted_by": dep,
                "reason": (
                    f"delivered on {rec.get('surface') or UNKNOWN_SOURCE} and "
                    f"rests on {dep}, which {went}: "
                    f"{str(rec.get('statement') or '')[:80]}"),
                "cascaded_from": dep,
            })
    # `retracted_by` is in the sort key as a SECOND line of defence, and it is
    # worth saying which line is first. Two entries about one row that lost two
    # of its bases agree on date, kind and claim_id - the whole of the old key
    # - so a stable sort leaves them in the order they were appended, and the
    # only reason that order is deterministic is that `_undermined_by` sorts
    # what it returns. Whichever of the two goes, the other still holds; both
    # going is what "same input, same output" would cost.
    ledger.sort(key=lambda r: (r["date"] or "", r["kind"], r["claim_id"],
                               r["retracted_by"] or ""))
    return ledger


def unenforceable_restrictions(datasets: dict) -> list[dict]:
    """A row that says it restricts something and names nothing (#75).

    Load-bearing facts keep arriving in prose the engine cannot read, and the
    sharpest recorded instance is this one: two `medical` rows carried, in the
    note, the words "RESTRICTION NOT ENFORCEABLE - no value in the restricts
    vocabulary expresses this". They were right, `restricts` was null, and for
    three days the record stated a restriction no gate could act on while the
    athlete trained inside it. The note announced its own unenforceability, in
    English, and that announcement was itself unreadable.

    MECHANICAL, NOT A PROSE SCAN. Reading notes for restriction-shaped
    sentences is a heuristic that would fire on the wrong rows and miss the
    quiet ones. Two shapes state a restriction in a field the engine already
    reads:

      `kind: restriction` with nothing in `restricts` - a row whose own
      declared kind says it is a restriction, naming nothing it restricts.

      A `precondition` with nothing in `restricts` - a check to clear a
      restriction that does not exist, so passing it clears nothing and
      failing it blocks nothing. THAT SHAPE IS ALREADY REFUSED AT APPEND, and
      a refusal where the cause is beats a finding in a later report - it is
      kept here because `append` covers writes through this engine and nothing
      else, and a row that arrived by sync or by hand is the one nothing has
      checked.

    The `kind: restriction` shape belongs in that same refusal, and this is
    not where it would go if `schema.py` were free. It is worth having both
    even then, for the reason #295 records: a rule forbidding something
    repairs nothing already written, and a finding reaches the rows a refusal
    never can.

    HEADS ONLY, so it clears itself. `medical` is identity-keyed, and a later
    row for the same slug that sets `restricts` is the repair; reporting the
    superseded line forever would be a finding that can never reach zero,
    which is the state #245 records people stop reading.
    """
    from .jsonl import heads

    out = []
    for slug, row in sorted(heads(datasets.get("medical") or [], "medical").items()):
        if str(row.get("restricts") or "").strip():
            continue
        if str(row.get("kind") or "") == "restriction":
            why = "its kind says it is a restriction"
        elif str(row.get("precondition") or "").strip():
            why = (f"it names {row['precondition']!r} as the check that would "
                   "clear it")
        else:
            continue
        out.append({
            "date": row.get("date"), "kind": "unenforceable_restriction",
            "severity": "review",
            "detail": (
                f"medical {slug!r} states a restriction and names nothing it "
                f"restricts: {why}, and `restricts` is empty. No gate can act "
                f"on it, so the record reads as restricted to a person and is "
                f"inert to the engine. If the vocabulary has no value for it, "
                f"that is a gap worth filing rather than working around in the "
                f"note"),
        })
    return out


def unsupported_assertions(ledger: list[dict]) -> list[dict]:
    """Things the engine TOLD somebody, whose basis has since moved (#134).

    The ledger already holds this once the cascade reaches emissions; this is
    the door that shouts. It is a projection rather than a second computation
    on purpose - two ways of deciding the same thing drift, and the one a
    reader sees would eventually disagree with the one a client queries.

    WHY THIS IS THE LOUD ONE. A stale derivation is a number in a file. An
    unsupported assertion was read by a person who may have changed what they
    did about it, and nothing else in the engine could tell them. That
    asymmetry - the record moved on and the person did not - is the whole
    complaint #134 files.

    Severity is `review` and never `error`. The engine cannot know whether the
    restatement changes what would be said now; asserting that it does would
    be the confident wrong answer, and asserting that it does not would be
    worse.
    """
    out = []
    for entry in ledger:
        if entry.get("kind") != "emission":
            continue
        out.append({
            "date": entry.get("date"), "kind": "unsupported_assertion",
            "severity": "review",
            "detail": (
                f"{entry['claim_id']} was {entry['reason']}. The assertion "
                f"stands as an event - it was made - but a reader acting on "
                f"it is acting on something the record no longer says the "
                f"same way"),
        })
    return out


def live_inferences(datasets: dict[str, list[dict]]) -> list[dict]:
    """Inferences whose justifications still stand.

    A retracted inference is not deleted - the record is history - but it
    stops being presented as current knowledge.
    """
    fallen = {r["claim_id"] for r in retractions(datasets) if r["kind"] == "inference"}
    return [r for r in datasets.get("inferences") or []
            if f"inference:{r.get('date')}:{r.get('model')}" not in fallen]


def _conservation(daily: list[dict], sessions: list[dict]) -> list[dict]:
    """The day cannot have burned less than its sessions did.

    Session kcal are an ATTRIBUTION of the day's burn, not an addition to it,
    so exceeding the day's measured total means a double-count or a bad
    source. Flagged, never fixed: the arithmetic is the symptom, and quietly
    rescaling it would erase the evidence.
    """
    burn = {d["date"]: d.get("kcal_out") for d in daily if d.get("date")}
    by_day: dict[str, float] = {}
    for s in sessions:
        if s.get("date") and _numeric(s.get("kcal")):
            by_day[s["date"]] = by_day.get(s["date"], 0.0) + float(s["kcal"])

    out: list[dict] = []
    for when in sorted(by_day):
        total = by_day[when]
        day_burn = burn.get(when)
        if not _numeric(day_burn):
            continue
        if total > float(day_burn) * (1.0 + ENERGY_TOLERANCE):
            out.append({
                "date": when,
                "kind": "sessions_exceed_day",
                "detail": (f"sessions attribute {total:.0f} kcal but the day's "
                           f"measured burn is {float(day_burn):.0f} - a "
                           "double-count or a wrong source, not extra energy"),
                "severity": "investigate",
            })
    return out


def _unattributed_losses(explanations: list[dict]) -> list[dict]:
    """A row with no source lost a contest, which is almost always an
    omission rather than a judgement (#73).

    Ranking an unattributed row last is a strong assertion - stronger than the
    evidence supports, because the commonest cause of a missing `source` is a
    writer that forgot rather than provenance nobody can establish. And the
    writers that forget are the first-hand ones, so the omission demotes the
    claims the ladder exists to promote.

    Reported, not corrected. Whether unattributed should rank last at all is a
    real question and changing it silently would be its own inversion; what
    was unacceptable was that it happened with no trace anywhere.
    """
    for e in explanations:
        if e.get("unattributed_loser"):
            yield {
                "date": e["date"],
                "kind": "unattributed_claim_lost",
                "detail": (
                    f"{e['dataset']}.{e['field']}: kept "
                    f"{e['chosen_source']}={e['chosen_value']} and discarded "
                    f"{e['discarded']} - a discarded claim carries no source, "
                    "so it ranked last by default. If that row has a source, "
                    "stamp it: an unattributed row loses every contest it "
                    "enters"),
                "severity": "review",
            }


def _unread_retired_values(datasets: dict[str, list[dict]]) -> list[dict]:
    """A line says something no successor field inherited.

    Two kinds of retirement, and only one of them is quiet by right. Where a
    forward map exists the old value reaches every reader as the new one, so an
    old line keeps working and there is nothing to report. Where the retirement
    is TERMINAL - a split into types the old value does not belong to - the
    successors stay empty, and staying empty with no comment is the part that
    is not defensible.

    NOT "THE VALUE IS LOST", and the difference is worth being exact about
    because this whole change is about a doc that overclaimed. The retired key
    is still a projected column: a consumer querying the table gets the string.
    What does not happen is anything built on the SUCCESSORS - grouping by
    `place`, the coarse egress tier, `route` - because those are null. The
    value is present and inert.

    NOT A PROBLEM AND NOT A CORRECTION. The line is not wrong: a retired key
    stays legal forever, and it was the right way to write it at the time. Nor
    does the engine guess; the remedy comes from the register, per key, because
    the two terminal retirements here need opposite advice.

    ONE PER FIELD, NOT ONE PER LINE. A record predating a retirement carries
    the old key across its whole history, and a tripwire per line would bury
    every other tripwire under a fact that is true once. Counted in LINES
    rather than rows, because these are raw claims: two devices logging one
    session are two lines and will resolve to one row.
    """
    from .schema import KEY_RETIREMENT, forward_map_for, terminal_retirement

    out = []
    for dataset in sorted(KEY_RETIREMENT):
        for key in sorted(KEY_RETIREMENT[dataset]):
            if forward_map_for(dataset, key) is not None:
                continue
            carrying = [r for r in datasets.get(dataset) or []
                        if r.get(key) is not None]
            if not carrying:
                continue
            why, remedy = terminal_retirement(dataset, key)
            # A dated line if there is one. A dataset can reach canonical
            # without dates, and a value there must still be reported rather
            # than filtered out by the field the report happens to sort on.
            dates = sorted(str(r["date"]) for r in carrying if r.get("date"))
            out.append({
                "date": dates[-1] if dates else "",
                "kind": "unread_retired_value",
                "detail": (
                    f"{len(carrying)} {dataset} line(s) carry `{key}`, retired "
                    f"at generation {KEY_RETIREMENT[dataset][key]}: {why}. The "
                    f"lines are valid and the column still holds what they "
                    f"said, but no successor field inherited it, so nothing "
                    f"derived from `{key}` reaches a report. To carry it "
                    f"forward, {remedy}"),
                "severity": "review",
            })
    return out


def _lineage_to_claim_id(ref: str) -> str | None:
    """A `derived_from` row reference as the claim id that can retire it.

    THE TWO GRAMMARS ARE NOT THE SAME and conflating them is a defect this
    engine has already shipped once. `derived_from` carries `identity.row_ref`
    (`dataset:date:source`, plus an ordinal when a date and source name more
    than one row); the retraction ledger carries `claim_id`
    (`dataset:date:source`, no ordinal). So the ordinal is dropped here and
    nothing else is assumed.

    Returns None for a reference that is not a claim id at all - an
    identity-keyed `sets` or `meals` row, whose middle part is a slug rather
    than a date -
    and the caller then declines to judge it. That is a deliberate
    false-negative: a ref this cannot translate is one whose retraction status
    is unknown, and reporting unknown as stale would be inventing a finding.
    """
    parts = ref.split(":")
    if len(parts) >= 4 and parts[-1].isdigit():
        parts = parts[:-1]
    if len(parts) != 3:
        return None
    # `sets` and `meals` key on an identity tuple rather than a date, so their
    # references are also three parts and are NOT claim ids. Requiring the
    # middle part to be a date is what tells the two shapes apart; without it
    # a meal reference translated into a plausible-looking id that could only
    # ever match by accident.
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[1]):
        return None
    return ":".join(parts)


def derivation_cycles(datasets: dict) -> list[dict]:
    """Lineage that leads back to where it started (#170).

    A row deriving from itself, or from something that derives from it, states
    a value it needs its own value to compute. It is the one lineage that can
    never be true, and it is what a naive exporter writes when it stamps a
    whole file with one reference.

    THIS IS SET-AWARE ON PURPOSE. `validate_record` sees one record and would
    compute ordinal 0 for every row, so it cannot tell a second same-day
    same-source reading deriving from the FIRST apart from a row deriving from
    itself, and rejecting the honest one is worse than missing the absurd one.
    With every row in hand the ordinals are real and the two can be told apart.

    One consequence worth knowing: an unnumbered reference means ordinal 0, so
    where a date and a source name several rows, a lineage that omits the
    ordinal points at the FIRST of them. A derived row that is itself first
    therefore names itself and is reported here, which is the right answer to
    what was written rather than a false positive - the fix is to write the
    ordinal.
    """
    from .identity import refs

    edges: dict[str, set] = {}
    where: dict[str, dict] = {}
    for dataset, rows in sorted(datasets.items()):
        if not rows or "derived_from" not in KEYS.get(dataset, []):
            continue
        for ref, row in zip(refs(dataset, rows), rows):
            lineage = row.get("derived_from") or []
            if lineage:
                edges[ref] = {str(x) for x in lineage}
                where[ref] = row

    def reaches(start: str, goal: str) -> bool:
        """Iterative on purpose. A recursive walk raised RecursionError at
        around a thousand links, and an honest daily derived series reaches
        that in three years - a build that dies on a long record is a worse
        failure than the loop it was looking for."""
        stack, seen = [start], set()
        while stack:
            for nxt in edges.get(stack.pop(), ()):  # declared lineage; no I/O
                if nxt == goal:
                    return True
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return False

    out = []
    for ref in sorted(edges):
        if not reaches(ref, ref):
            continue
        out.append({
            "date": where[ref].get("date"),
            "kind": "derivation_cycle",
            "severity": "error",
            "detail": (
                f"{ref} is derived, directly or through other rows, from "
                f"itself. A value cannot be an input to its own computation, "
                f"so one of the references in this loop is wrong"),
        })
    return out


def stale_derivations(datasets: dict, retracted: set) -> list[dict]:
    """Values standing on an input the record has since restated (#170).

    Declared lineage is enough to DETECT this, which is the whole reason
    `derived_from` is a list of references rather than a re-execution plan:
    declared lineage suffices for staleness detection, and re-execution would
    only be needed to CORRECT the drift, which this engine does not do.

    REPORTED, NEVER RECOMPUTED, and the value is left exactly where it is. The
    engine does not know how the number was derived - `derived_op` is free text
    and declared non-executable - so it cannot produce a corrected one, and
    inventing one would be the confident wrong answer a visible flag beats.

    WHAT IT CAN AND CANNOT TELL, stated plainly because the wording of the
    finding depends on it. A row reference names a date and a source, not a
    particular version of that row, so a lineage naming a corrected input reads
    identically whether it was computed from the old value or the new one. The
    engine cannot distinguish those, so the finding does not claim to: it
    reports that the value behind the reference was restated and leaves the
    reader to check which version this derivation used. Saying "this is stale"
    would be a guess wearing the engine's voice.
    """
    from .identity import refs

    # Every derived row, by its own reference, with what it stands on.
    stands_on: dict[str, set] = {}
    rows_by_ref: dict[str, tuple] = {}
    for dataset, rows in sorted(datasets.items()):
        if not rows or "derived_from" not in KEYS.get(dataset, []):
            continue
        for ref, row in zip(refs(dataset, rows), rows):
            if row.get("derived_from"):
                stands_on[ref] = {str(x) for x in row["derived_from"]}
                rows_by_ref[ref] = (dataset, row)

    # Seed with rows standing DIRECTLY on something restated, then propagate:
    # a value computed from a stale value is stale too. This is the cascade
    # `retractions` already runs for inferences, on the same reasoning - a
    # belief resting on a belief whose evidence moved has to move with it -
    # and without it "everything computed from this" would mean "one hop".
    direct = {ref: sorted({r for r in lineage
                           if _lineage_to_claim_id(r) in retracted})
              for ref, lineage in stands_on.items()}
    stale = {ref: list(hits) for ref, hits in direct.items() if hits}
    changed = True
    while changed:                      # terminates: `stale` only ever grows
        changed = False
        for ref, lineage in stands_on.items():
            if ref in stale:
                continue
            if via := sorted(lineage & set(stale)):
                stale[ref] = via
                changed = True

    out = []
    for ref in sorted(stale):
        dataset, row = rows_by_ref[ref]
        moved = stale[ref]
        # Built outside the f-string: a conditional spanning lines inside one
        # is 3.12 syntax, and this package supports 3.11.
        one = len(moved) == 1
        if direct.get(ref):
            what = ("the value behind that reference has"
                    if one else "the values behind those references have")
            what += " been restated"
        else:
            # Inherited. Saying "restated" here would be false: this row's own
            # inputs are untouched, and what moved is further back.
            what = ("that reference is itself stale"
                    if one else "those references are themselves stale")
        out.append({
            "date": row.get("date"),
            "kind": "stale_derivation",
            "severity": "review",
            "detail": (
                f"{ref} was computed from {', '.join(moved)}, and {what}."
                f" Check which version this derivation used: a row reference"
                f" names a date and a source rather than a version, so the"
                f" engine cannot tell. It is not recomputed either -"
                f" `derived_op` is declared rather than executable"),
        })
    return out


def apply_regimes(canonical: dict, regimes: list[dict]) -> list[dict]:
    """Empty the days a declared regime covers. Never backfill them.

    A regime is a bounded interval during which a class of claims was
    UNANCHORED: an ill-defined measurand honestly restated. High trust, low
    accuracy, sustained, which is the empirical proof that trust and accuracy
    are different axes (#171).

    INVALIDATES WITHOUT REPLACING, and this is the part that is easy to get
    wrong. The measurement that ENDED the regime is evidence that the earlier
    claims were unanchored. It is NOT evidence of what the true values were.
    So the covered field goes null and nothing is interpolated, extrapolated
    or carried back: a blank beats a confident wrong number, applied to an
    interval instead of to a cell.

    THE CLAIMS ARE NOT DELETED. They stay where they are, in the file and in
    `claims`, because append-only means a record never loses what it was told.
    What ends is their standing as values.

    TRUST INVARIANCE, a hard constraint: applying a regime touches no trust,
    credibility or dominance parameter of the athlete or of any source. There
    is no such parameter in this engine, by design, and this rule is part of
    what keeps it that way. Discovering your own error must never cost you
    standing: trust is about intent and care, accuracy is about the number,
    and self-correction is evidence of care rather than against it.

    Returns tripwires. `canonical` is edited in place; the caller owns it.
    """
    out = []
    for regime in regimes:
        dataset, field = regime.get("dataset"), regime.get("field")
        first, last = regime.get("from_date"), regime.get("to_date")
        if not (dataset and field and first and last):
            continue
        emptied = 0
        for row in canonical.get(dataset) or []:
            when = str(row.get("date") or "")
            if not (first <= when <= last) or row.get(field) is None:
                continue
            # Scoped to one source where the athlete narrowed it: a regime
            # about a bathroom scale must not empty a clinic measurement
            # taken in the same weeks.
            if regime.get("source") and row.get("source") != regime["source"]:
                continue
            row[field] = None
            emptied += 1
        if emptied:
            out.append({
                "date": first,
                "kind": "unanchored_interval",
                "severity": "review",
                "detail": (
                    f"{dataset}.{field} is empty from {first} to {last} "
                    f"({emptied} day(s)): a declared regime says those claims "
                    f"were unanchored. {regime.get('text') or ''} The readings "
                    f"are still in the record and nothing was filled in behind "
                    f"them, because what ended the regime is evidence the "
                    f"earlier claims were unanchored rather than evidence of "
                    f"what the true values were"),
            })
    return out


def restatement_runs(canonical: dict) -> list[dict]:
    """Runs of identical values in quantities the world makes vary.

    A number repeated unchanged across days, in a quantity that moves, is
    evidence that it was RESTATED rather than observed: somebody wrote down
    what they remembered, a device repeated a cached reading, or an import
    carried one value across days it never covered.

    THE SAME CONCEPT `provenance.restatements` RANKS, reached from the other
    side. There, the record SAYS how a value was acquired (`capture:
    narrative`) and the rank follows from the statement. Here the record says
    nothing, and the shape of the series is the only evidence there is. One
    phenomenon, two evidence routes; neither replaces the other, because a
    record can lie about capture and a restated series can be honestly
    labelled.

    ADVISORY, always, and the registry is open: a field absent from
    `semantics/variation.toml` is never checked, and an omission accuses
    nobody. Some true series are genuinely flat - a maintenance phase on a
    coarse scale, a layoff - and a detector that failed a build on one would
    be asserting that a record is wrong for being boring.
    """
    from .vocab import registry
    spec = registry("variation")["variation"]
    out = []
    for dataset, fields in sorted(spec.items()):
        rows = canonical.get(dataset) or []
        for field, rule in sorted(fields.items()):
            out += _runs_in(dataset, field, rows, rule)
    return out


def _runs_in(dataset: str, field: str, rows: list[dict],
             rule: dict) -> list[dict]:
    """Every constant run of this field long enough to be worth saying."""
    dated = sorted(
        ((str(r.get("date")), r.get(field)) for r in rows
         if r.get("date") and r.get(field) is not None),
        key=lambda pair: pair[0])
    if not dated:
        return []
    window = int(rule.get("window_days", 5))
    out, start = [], 0
    for i in range(1, len(dated) + 1):
        same = i < len(dated) and dated[i][1] == dated[start][1]
        if same:
            continue
        first, last = dated[start][0], dated[i - 1][0]
        # SPAN IN DAYS, not row count. Three readings on one morning are one
        # observation restated twice, not three days of agreement, and a
        # row-count rule would have called that a flat week.
        if i - start >= 2 and _days_between(first, last) + 1 >= window:
            out.append({
                "date": first,
                "kind": "constant_value_run",
                "severity": "review",
                "detail": (
                    f"{dataset}.{field} held exactly {dated[start][1]} from "
                    f"{first} to {last}, which is {_days_between(first, last) + 1} "
                    f"days. {rule.get('note', '')} If this is real, a regime "
                    f"declaration says so; if it is a value carried forward, "
                    f"the reading it was carried from is the one observation "
                    f"here"),
            })
        start = i
    return out


def _days_between(first: str, last: str) -> int:
    from datetime import date as _date
    return (_date.fromisoformat(last) - _date.fromisoformat(first)).days


def _contradictions(explanations: list[dict]) -> list[dict]:
    """High-precedence sources disagreeing beyond tolerance is worth saying.

    A CORRECTION is not a disagreement (#70). Two claims from one source are
    the same instrument twice, and the later one supersedes the earlier - so
    raising "mfp-export says 3091, mfp-export says 1354" reports the
    correction mechanism working as a fault.

    But a CAPTURE-decided contest is not the correction mechanism (#140). It
    is a device reading and a recollection of the same instrument disagreeing,
    which is the thing that issue is about - and it shared a source, so the
    skip above swallowed it at any spread. A scale reading of 80.4 and a
    remembered 74.0 left nothing but an explanations row.
    """
    for e in explanations:
        if (e.get("chosen_source") == e.get("over_source")
                and not e.get("by_capture")):
            continue
        if e.get("disagreed") and _numeric(e.get("chosen_value")) \
                and _numeric(e.get("over_value")):
            # NAMES WHAT WAS DISCARDED, not the runner-up. `disagreed` now
            # answers "is there a disagreement here" over EVERY discard, so
            # the pair the ladder happened to decide can be two claims that
            # agree - a scale and an app both saying 70.0 while a watch says
            # 84.5 produced a `source_disagreement` reading "app says 70.0,
            # scale says 70.0", which looks like the tripwire is broken.
            #
            # `discarded` is already on the row and already lists all of them,
            # so this needs no new column: the tripwire's job is to say look
            # here, and the spread is what a reader has to look at.
            yield {
                "date": e["date"],
                "kind": "source_disagreement",
                "detail": (f"{e['dataset']}.{e['field']}: "
                           f"{e['chosen_source']} says {e['chosen_value']}, "
                           f"against {e['discarded']}"),
                "severity": "review",
            }
