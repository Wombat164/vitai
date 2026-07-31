"""Many claims, one canonical truth (G15) - the conservation golden rule.

A calorie is eaten once and burned once. When a watch says 2,443 kcal and a
calorie app says 2,844 kcal for the same day, the record does not hold both,
and it certainly does not hold 5,287. It holds ONE canonical value chosen by
precedence, with both claims retained as observations and the choice
explained.

This runs at build time, BEFORE any derivation. Everything downstream - the
rollup, verdicts, contributions, the read model's primary tables - consumes
canonical rows. Raw claims are projected into companion `*_claims` tables for
anyone who wants to audit the adjudication.

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

from datetime import datetime, timedelta

from .clocks import comparable, is_aware, parse_time, stamp_instant
from .provenance import (TRUST_ORDER, describe, distinct_origins,
                         independent_witnesses, shares_origin, trust_ceiling)

from .schema import KEYS

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
NON_QUANTITY_FIELDS = {"date", "source", "origin", "path", "origin_evidence"}


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
    return isinstance(v, (int, float)) and not isinstance(v, bool)


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

    for field in KEYS[dataset]:
        if field in NON_QUANTITY_FIELDS:
            continue
        witnesses = [(cid, rec) for cid, rec in claims if rec.get(field) is not None]
        if not witnesses:
            canonical[field] = None
            continue
        ladder = _ladder(field, precedence, default)
        witnesses.sort(key=lambda w: (_rank(w[1].get("source"), ladder),
                                      *_recency(w[1])))
        winner_id, winner = witnesses[0]
        canonical[field] = winner[field]
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
            explanations.append({
                "date": winner.get("date"),
                "dataset": dataset,
                "field": field,
                "chosen_source": winner.get("source") or UNKNOWN_SOURCE,
                "chosen_value": winner[field],
                "over_source": loser.get("source") or UNKNOWN_SOURCE,
                "over_value": loser[field],
                "witnesses": independent_witnesses(witness_recs),
                "reason": _why(winner.get("source"), loser.get("source"), ladder),
                "disagreed": _disagrees(winner[field], loser[field]),
                # Same origin means these are one measurement seen at two
                # points on one pipe. The spread then measures PIPELINE
                # FIDELITY, not truth - worth reporting, never worth counting
                # as validation (#51).
                "independent": not shares_origin(winner, loser),
                "compares": ("pipeline fidelity" if shares_origin(winner, loser)
                             else "independent observations"),
            })
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
    """
    when = stamp_instant(rec.get("recorded_at"))
    return (1, 0.0) if when is None else (0, -when.timestamp())


def _why(winner: object, loser: object, ladder: tuple[str, ...]) -> str:
    w, ll = str(winner or UNKNOWN_SOURCE), str(loser or UNKNOWN_SOURCE)
    # Same source on both sides means precedence decided nothing - recency
    # did. Saying "mfp-export outranks mfp-export" is false, and it is false
    # in the audit trail, which is the one place the record explains itself.
    if w == ll:
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
    return canonical


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

    tripwires += _conservation(canonical["daily"], canonical["sessions"])
    tripwires += [t for t in _contradictions(explanations)]
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


def _dependencies(rec: dict) -> list[str]:
    """The claim ids an inference declares it rests on."""
    raw = rec.get("depends_on")
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [part.strip() for part in str(raw).replace(",", " ").split() if part.strip()]


def retractions(datasets: dict[str, list[dict]]) -> list[dict]:
    """The JTMS ledger: what stopped being true, and what fell with it.

    A correction does not merely replace a number - it revokes the
    justification that number was holding up. Anything resting on it has to
    come down too, or the record keeps a belief whose evidence no longer
    exists ("stroller pace" surviving after the athlete says there was no
    child). This is the labeled-assumption-set + cascade-invalidate rule from
    JTMS (Doyle 1979), and deliberately nothing more: no full ATMS, no
    LLM-assigned confidence. Confidence is a property of tier and source.
    """
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
    for rec in datasets.get("inferences") or []:
        fallen = sorted(set(_dependencies(rec)) & retracted)
        for dep in fallen:
            ledger.append({
                "date": rec.get("date"), "kind": "inference",
                "claim_id": f"inference:{rec.get('date')}:{rec.get('model')}",
                "retracted_by": dep,
                "reason": (f"rests on {dep}, which was retracted: "
                           f"{str(rec.get('statement') or '')[:80]}"),
                "cascaded_from": dep,
            })
    ledger.sort(key=lambda r: (r["date"] or "", r["kind"], r["claim_id"]))
    return ledger


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


def _contradictions(explanations: list[dict]) -> list[dict]:
    """High-precedence sources disagreeing beyond tolerance is worth saying.

    A CORRECTION is not a disagreement (#70). Two claims from one source are
    the same instrument twice, and the later one supersedes the earlier - so
    raising "mfp-export says 3091, mfp-export says 1354" reports the
    correction mechanism working as a fault.
    """
    for e in explanations:
        if e.get("chosen_source") == e.get("over_source"):
            continue
        if e.get("disagreed") and _numeric(e.get("chosen_value")) \
                and _numeric(e.get("over_value")):
            yield {
                "date": e["date"],
                "kind": "source_disagreement",
                "detail": (f"{e['dataset']}.{e['field']}: "
                           f"{e['chosen_source']} says {e['chosen_value']}, "
                           f"{e['over_source']} says {e['over_value']}"),
                "severity": "review",
            }
