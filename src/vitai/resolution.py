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

from .schema import KEYS

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
NON_QUANTITY_FIELDS = {"date", "source"}


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

    for field in KEYS[dataset]:
        if field in NON_QUANTITY_FIELDS:
            continue
        witnesses = [(cid, rec) for cid, rec in claims if rec.get(field) is not None]
        if not witnesses:
            canonical[field] = None
            continue
        ladder = _ladder(field, precedence, default)
        witnesses.sort(key=lambda w: _rank(w[1].get("source"), ladder))
        winner_id, winner = witnesses[0]
        canonical[field] = winner[field]
        justifications.append({
            "field": field,
            "claim_id": winner_id,
            "source": winner.get("source") or UNKNOWN_SOURCE,
            "tier": "observed",
            "quantity_class": QUANTITY_CLASS.get(dataset, "measured_flow"),
            "witnesses": len(witnesses),
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
                "witnesses": len(witnesses),
                "reason": _why(winner.get("source"), loser.get("source"), ladder),
                "disagreed": _disagrees(winner[field], loser[field]),
            })
    return canonical, justifications, explanations


def _why(winner: object, loser: object, ladder: tuple[str, ...]) -> str:
    w, ll = str(winner or UNKNOWN_SOURCE), str(loser or UNKNOWN_SOURCE)
    if w in ladder and ll not in ladder:
        return f"{w} is ranked for this quantity, {ll} is not"
    if w in ladder and ll in ladder:
        return f"{w} outranks {ll} for this quantity"
    return f"neither source is ranked; {w} sorts first"


def _carry_meta(canonical: dict, claims: list[tuple[str, dict]]) -> dict:
    """Keep the highest schema generation seen, so a merged row is not
    mistaken for an older-shaped one."""
    gens = [c.get("_gen") for _, c in claims if isinstance(c.get("_gen"), int)]
    if gens:
        canonical["_gen"] = max(gens)
    return canonical


# --- session activity identity ------------------------------------------------

def _interval(rec: dict) -> tuple[datetime, datetime] | None:
    if not (st := rec.get("start_time")):
        return None
    try:
        start = datetime.fromisoformat(str(st))
    except ValueError:
        return None
    seconds = rec.get("duration_s") if _numeric(rec.get("duration_s")) else 0
    return start, start + timedelta(seconds=float(seconds or 0))


def _ratio(a: object, b: object) -> float | None:
    if not (_numeric(a) and _numeric(b)) or not float(b):
        return None
    return float(a) / float(b)


def _same_activity(a: dict, b: dict) -> tuple[bool, bool]:
    """(same, near_miss) for two session claims on one date.

    Timestamps win when both sides have them: two platforms recording one run
    describe overlapping intervals, and nothing else does. Without times the
    test falls back to shape - same type, similar duration, similar distance -
    which is weaker, so anything landing just outside the bands is reported as
    a near miss rather than quietly treated as distinct.
    """
    ia, ib = _interval(a), _interval(b)
    if ia and ib:
        overlaps = ia[0] < ib[1] and ib[0] < ia[1]
        if overlaps:
            return True, False
        gap = min(abs((ia[0] - ib[1]).total_seconds()),
                  abs((ib[0] - ia[1]).total_seconds()))
        return False, gap <= 600 and a.get("type") == b.get("type")
    if a.get("type") != b.get("type"):
        return False, False

    dur = _ratio(a.get("duration_s"), b.get("duration_s"))
    dist = _ratio(a.get("distance_km"), b.get("distance_km"))
    if dur is None and dist is None:
        return False, False

    def within(r: float | None, band: tuple[float, float], slack: float) -> bool:
        return r is None or band[0] - slack <= r <= band[1] + slack

    same = (within(dur, DURATION_RATIO, 0.0) and within(dist, DISTANCE_RATIO, 0.0))
    near = (not same
            and within(dur, DURATION_RATIO, NEAR_MISS_SLACK)
            and within(dist, DISTANCE_RATIO, NEAR_MISS_SLACK))
    return same, near


def _richness(rec: dict) -> int:
    return sum(1 for v in rec.values() if v is not None)


def _cluster_sessions(claims: list[tuple[str, dict]]) -> tuple[list[list[tuple[str, dict]]],
                                                               list[dict]]:
    """Group one date's session claims into physical activities."""
    clusters: list[list[tuple[str, dict]]] = []
    near_misses: list[dict] = []
    for cid, rec in claims:
        placed = False
        for cluster in clusters:
            same, near = _same_activity(cluster[0][1], rec)
            if same:
                cluster.append((cid, rec))
                placed = True
                break
            if near:
                near_misses.append({
                    "date": rec.get("date"),
                    "kind": "near_miss_duplicate",
                    "detail": (f"{rec.get('source') or UNKNOWN_SOURCE} and "
                               f"{cluster[0][1].get('source') or UNKNOWN_SOURCE} "
                               f"logged similar {rec.get('type')} sessions that "
                               "did not match closely enough to merge"),
                    "severity": "review",
                })
        if not placed:
            clusters.append([(cid, rec)])
    return clusters, near_misses


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
                merged = _carry_meta(merged, group)
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

    return {"canonical": canonical, "claims": claims_out,
            "explanations": explanations, "justifications": justifications,
            "tripwires": tripwires}


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
    """High-precedence sources disagreeing beyond tolerance is worth saying."""
    for e in explanations:
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
