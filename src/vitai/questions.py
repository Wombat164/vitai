"""What the record does not know about what is coming (#224, the floor).

Everything else in this engine runs one way: a client asks, the engine answers
or refuses. This is the inversion - the engine holding a question the record
cannot settle. It is the FLOOR of that channel and deliberately nothing above
it: a deterministic derivation over the record, computable with no model
configured, no network, no permission layer and no budget.

DERIVE FEW, DO NOT GENERATE MANY AND SUPPRESS. The tempting build is an
enumerator over every unknown plus a relevance filter above it. That inverts
the property the channel most needs. The engine's urge to ask peaks exactly
where asking is least welcome - a long disengaged stretch produces the most
unresolved plans and the most unanswered anything - and it is precisely the
period somebody has deliberately stepped away from. If the filtering lives in
the budget layer, the safety property depends on the accelerator being built
and switched on.

So a question exists only where an answer would change SOMETHING THAT HAS NOT
HAPPENED YET. Every question here hangs off a plan that is still ahead, which
is what makes a dormant period generate none: nothing is planned, so nothing
is asked, with no filter doing the work and nothing to switch off.

IT DOES NOT ASK ANYBODY, and that is the boundary of this piece rather than an
omission. There is no surface here that speaks, no ordering by urgency beyond
the day a thing is planned for, and `nudge_ok` is not read - it defaults off
and has no consumer yet. What that means for G82's first rule, that a decline
is permanent and is itself an answer: nothing can be declined yet because
nothing can be asked, and a decline needs somewhere of its own to live. That
lands with the surface that asks, and until then this is a computation a
client reads rather than a channel that speaks.

THE ENGINE WRITES NO SENTENCES, and that is a narrower claim than "no field
here is prose" - which was the first wording and was false. `id`, `kind`,
`for_date` and `settled_by` are the engine's, and every one is a slug, a date
or a closed vocabulary: a question the engine phrased would be the engine
deciding how it sounds, and "no question may imply a duty" lives entirely in
phrasing, so the wording belongs to whatever asks. Same shape `corrections.py`
landed on, for the same reason.

But `subject` and `bears_on` are the RECORD'S OWN WORDS, passed through
unaltered. `plans.requires` is not slug-checked anywhere - nothing stops an
athlete writing a sentence there, including a clinician's name or why - and
this hands it to a consumer under a field a docstring once called a slug.
Downstream that matters: it is a surface record text leaves through, and
whatever asks has to treat it as content rather than as an identifier.
"""

from __future__ import annotations

from datetime import date

# What kind of unknown this is. Closed, and short on purpose: a vocabulary
# that grows by guesswork is how "unusual" arrives as a category.
KINDS = frozenset({"precondition", "clearance"})

# Who or what could settle it. This is the field that lets something other than
# a person answer, which is the whole reason a question says what would settle
# it rather than only what it is about.
#
# NO `lookup` YET, and its absence is a decision. Whether "dry-forecast" is
# settleable by a weather service or only by the athlete is a claim about the
# world that this record cannot check, and the outward lookup is a later part
# of this channel with a permission layer under it. Naming one here would be
# the engine asserting a capability nothing has. So a precondition falls to the
# answerer who always exists, and a client that knows a lookup would serve is
# free to use one.
SETTLED_BY = frozenset({"athlete", "check"})


def _as_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def ahead(plans: list[dict], on: date) -> list[dict]:
    """Plans for today or later, in the order they come up.

    THE RELEVANCE FILTER, and it is a safety mechanism rather than noise
    reduction. Everything asked here hangs off one of these, so a record with
    nothing planned produces nothing to ask - which is the property a
    disengaged stretch needs, arrived at by construction rather than by a rule
    that could be relaxed.

    A resolved plan is not ahead of anybody even if its date is: the athlete
    has already said what happened, and asking again is asking twice.

    THE LATEST ROW PER SLUG, and asking that per ROW was wrong. A plan is
    resolved by a SECOND ROW carrying the same slug - that is the documented
    lifecycle, because an honestly unresolved plan was not WRONG and a
    correction says a line was. Filtering row by row therefore kept the
    original, still unresolved, and went on asking a question the athlete had
    already answered - and where a plan had been re-dated it produced two
    questions sharing one id, which is the id's whole purpose gone.
    """
    latest: dict[str, dict] = {}
    for plan in plans:
        latest[str(plan.get("slug"))] = plan
    out = []
    for plan in latest.values():
        when = _as_date(plan.get("for_date"))
        if when is None or when < on:
            continue
        if str(plan.get("outcome") or "unresolved") != "unresolved":
            continue
        out.append(plan)
    return out


def open_questions(plans: list[dict], gates_on_day, on: date) -> list[dict]:
    """One row per thing the record does not know about a plan still ahead.

    Two kinds today, and both are questions whose answer changes whether or
    how the thing happens rather than only what the record says about it:

      `precondition` - the plan names a condition it needs and the record
      holds no answer. "I would run if it were dry" with nothing saying
      whether it is. What would settle it is the athlete or a lookup, and
      naming that is what lets something other than a person answer.

      `clearance` - the plan's activity is gated and the gate is waiting on a
      check nobody has done. Three states exist there for a reason: "your leg
      said no today" and "you have not asked it yet" are different facts, and
      only the second is a question. A check settles it.

    A GATE THAT IS SIMPLY BLOCKED IS NOT A QUESTION. Nothing the athlete can
    say changes it, so asking would be asking somebody to talk their way past
    a clinical hold.
    """
    out = []
    for plan in ahead(plans, on):
        slug = str(plan.get("slug"))
        if (needs := str(plan.get("requires") or "").strip()):
            out.append({
                "id": f"plans:{slug}:requires",
                "kind": "precondition",
                "about": slug,
                "for_date": str(plan.get("for_date")),
                "subject": needs,
                "settled_by": "athlete",
                "bears_on": str(plan.get("activity") or "").strip(),
            })
        for gate in gates_for(plan, gates_on_day):
            out.append({
                "id": f"plans:{slug}:clearance:{gate}",
                "kind": "clearance",
                "about": slug,
                "for_date": str(plan.get("for_date")),
                "subject": gate,
                "settled_by": "check",
                "bears_on": str(plan.get("activity") or "").strip(),
            })
    return sorted(out, key=lambda q: (q["for_date"], q["id"]))


def gates_for(plan: dict, gates_on_day) -> list[str]:
    """The gates waiting on a check that cover this plan's activity.

    MATCHED BY THE ENGINE'S OWN RULE, not by one restated here. `restricts` is
    validated against activity CLASSES - `impact`, `lower_body`, `all` - and
    `is_gated` expands the activity through the registry before comparing, so
    a gate spelled `impact` blocks a planned `run`. Comparing the strings
    instead, which is what this did first, silently missed every gate not
    spelled as the exact activity: `may("run")` said blocked, the gate said
    `check_not_done`, and the derivation whose job is to surface exactly that
    check returned nothing. A false negative on the safety-relevant kind.

    EVALUATED ON THE PLAN'S OWN DAY. Gates were read on the viewpoint day and
    attached to plans for later ones, which was wrong twice: a check passing
    today cleared the gate and silenced the question about next Saturday,
    which reappeared tomorrow, and an episode with a `resolved_date` before
    the plan produced a question the record already answered.
    """
    from .safety import is_gated, undecidable_scope

    activity = str(plan.get("activity") or "").strip()
    if not activity:
        return []
    for_day = _as_date(plan.get("for_date"))
    gates = gates_on_day(for_day) if for_day is not None else []
    # AN UNDECIDABLE GATE IS NOT A QUESTION FOR THE ATHLETE. `is_gated` counts
    # one as gating, which is the right answer for a bool on a safety surface -
    # but a clearance question asserts that doing the check lifts this
    # restriction, and nobody can know that when the scope does not parse. The
    # athlete would do a hop test that settles nothing, and a passing check
    # would then mark the gate `cleared`, at which point `may` skips it and
    # answers `allowed` on a record still holding a broken token.
    #
    # UNDECIDABLE FOR THIS ACTIVITY, not unreadable in general, and the
    # difference is a regression this already caused once. A gate reading
    # `restricts: "impact zzz-typo"` blocks a run on `impact` perfectly well;
    # testing the gate-only predicate silenced the hop-test question that was
    # genuinely the way out, because of an unrelated second word.
    waiting = [g for g in gates if g.get("status") == "check_not_done"
               and not undecidable_scope(g, activity)]
    return sorted({str(g.get("slug")) for g in waiting
                   if is_gated([g], activity)})
