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

A THIRD KIND, `waking` (#212), which answers a question the other two cannot
even ask about: not what is coming, but what a day that already happened
cannot be understood without. `clocks.day_phase` derives which part of the
athlete's own day a weigh-in or a session fell in, anchored on when they woke,
and a day with no sleep row behind it gets no phase - not "probably morning",
because that inference was tried on this issue and retracted: a logging habit
and a waking window are indistinguishable in the record, and the proposal
would be confidently wrong for the athlete the feature exists for. So the only
mechanism left is to ask, and `waking_questions` is where that lands. See its
own docstring for the worth-asking rule, which is the substance of this kind.

A FOURTH AND A FIFTH (#398), from a real outage: a charger left at home, and a
watch that first fell quiet and then, on its last charge, reported a day the
athlete spent moving as `steps: 0`. `outage` names the run of silence and
`false_zero` names the fabricated measurement, and they are two kinds rather
than one list because they want opposite gestures - an append against a day
with no row, a supersede against a row that exists and is wrong. See the
comment above `false_zero_questions` for why the second is the dangerous one
and why neither rule carries a number.
"""

from __future__ import annotations

from datetime import date, timedelta

# What kind of unknown this is. Closed, and short on purpose: a vocabulary
# that grows by guesswork is how "unusual" arrives as a category.
KINDS = frozenset({"precondition", "clearance", "waking", "outage",
                   "false_zero"})

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


def waking_questions(phase_rows: list[dict], on: date) -> list[dict]:
    """One question per day the record could place if it knew when the
    athlete woke (#212), from `Vitai.phases()`'s own output.

    THE OBVIOUS BUILD IS WRONG, AND IT IS WRONG BY A LOT. "Ask about every
    unanchored day" was measured against the shipped persona corpus while
    designing this: several personas that have never logged a sleep row carry
    hundreds of unanchored weigh-ins each, one has over two thousand. Asking
    about every one of them is the exact failure this module's own docstring
    names for plans - the channel that is supposed to protect the athlete's
    attention becomes the thing that exhausts it, worst on the record that
    has gone longest without a confirmed waking to anchor against.

    WORTH ASKING IS ONE CONDITION - RECENCY - and it is structural rather
    than a number picked because it felt right (G85: no invented threshold
    where a principled rule exists).

    A DAY phases() CANNOT PLACE IS A CANDIDATE THE MOMENT IT EXISTS, whether
    it carries one unanchored row or several. An earlier version of this
    rule also required two or more unanchored rows on the day, reasoning
    that a lone reading "has nothing for a phase to disambiguate" - and that
    reasoning did not survive being checked against #212's own text. The
    issue names three things a phase fixes: two same-day readings that stop
    merging, a narrative claim that becomes matchable against a device claim
    ("the athlete says 'morning weigh-in'; the scale says 07:36"), and a
    disagreement that gets a shape. The second of those IS the single-row
    case - a lone reading is what a stated phase would confirm or
    contradict - so requiring multiplicity silenced that motivation
    permanently, on every record, forever.

    WHAT ASKING BUYS TODAY IS NARROWER THAN THAT SOUNDS, and saying so is
    the point: no weight or session row can carry a stated phase yet -
    `for_phase` exists on `plans` and on nothing else - so answering
    compares nothing against anything the moment it lands. What the answer
    supplies is the ANCHOR such a comparison would need, a waking that lets
    `phases()` place the row at all. That is still worth asking for, on two
    grounds that do not depend on the comparison ever being built: the
    anchor is the part only the athlete holds, and it is the part that gets
    harder to recall with every week that passes. So this is a prerequisite
    being collected rather than a check being run, and a docstring implying
    otherwise would be the overclaim this rewrite exists to remove.

    ONLY THE MOST RECENT QUALIFYING DAY PER DATASET IS ASKED ABOUT, and this
    - not multiplicity - is what bounds the volume. Not a day-count cutoff:
    there is no published number of days after which a waking is
    unrecallable, and inventing one would be the same mistake #212 already
    made once and retracted, a fabricated precision dressed as a rule.
    "Most recent" needs no number: it is simply the day closest to the
    record's own horizon, which is both the one the athlete is likeliest to
    still remember and the one most likely to still matter to something
    unresolved. Older qualifying days are not hidden - `phases()` keeps
    reporting them as unanchored - they are just not competing for the one
    channel this floor has. Answering the asked day (by logging a
    `daily.sleep_end` for it, the same field and the same append any other
    waking is recorded with) removes it from the unanchored set, and the
    next call surfaces whichever day is then most recent. The backlog
    drains one question at a time, on its own, with no accelerator and
    nothing to switch on. BOUNDED BY CONSTRUCTION rather than by counting:
    at most one day per dataset can ever be "the newest", no matter how many
    unanchored days sit behind it or how long the record runs.

    CAPPED PER DATASET, NOT GLOBALLY, because `weight` and `sessions` feed
    different consumers with different stakes - a same-day weigh-in pair
    disambiguated by phase is a different fact from a same-day session
    matched to the right plan - and a backlog on one must not silence the
    other. Two datasets carry a time (`PHASE_FIELD` in `api.py`), so this
    asks at most two questions at once, record-wide, regardless of how deep
    either backlog runs.

    MEASURED ON THE SHIPPED CORPUS, not asserted, before AND after dropping
    multiplicity - the claim that multiplicity was the volume control was
    itself measured and found false. With multiplicity in place: five
    questions across thirteen personas and the demo. With it dropped and
    only recency left: eighteen, and still at most two per record (one per
    dataset), because most of a backlog's unanchored days are not the one
    closest to the record's own horizon and so never win recency for their
    dataset. Recency was already doing the volume control credited to
    multiplicity; dropping multiplicity only widens what recency was
    already bounding, it does not remove the bound.

    `on` is the valid-time viewpoint (`Vitai.on`, or a caller's override): a
    day after it has not been reached yet from where the record is being
    read, so it is excluded the same way `ahead()` excludes a plan whose date
    has not arrived - the mirror image, since these rows are already in the
    past rather than still ahead, but the same discipline against answering
    for a future the viewpoint has not seen.

    THE SHAPE DIFFERS FROM `precondition`/`clearance` ON PURPOSE. There is no
    plan slug to hang `about` from and no free-text field to pass through as
    `subject` - the record never wrote a sentence about this day, only
    timestamps - so `resolves` carries those timestamps verbatim instead: the
    record's own values, not the engine's words, which is the same rule
    `subject` follows for a precondition, applied to a kind that has numbers
    where a precondition has prose.
    """
    # UNANCHORED ROWS, GROUPED BY DATASET AND THE DAY THEY SHARE. A row
    # phases() already resolved is not a question - it is a fact - so only
    # `phase is None` rows are candidates, and `anchored_on` is not read: an
    # anchor that turned out incomparable (#38, naive against aware) is
    # exactly as unusable to the athlete's answer as no anchor at all.
    by_dataset: dict[str, dict[str, list[dict]]] = {}
    for row in phase_rows:
        if row.get("phase") is not None:
            continue
        when = _as_date(row.get("date"))
        if when is None or when > on:
            continue
        dataset, day = str(row["dataset"]), str(row["date"])
        by_dataset.setdefault(dataset, {}).setdefault(day, []).append(row)

    # RECENCY, per dataset - the one condition, and the whole volume control.
    # ISO dates compare lexically in date order, so `max` over the keys is
    # the newest qualifying day with no parsing.
    out = []
    for dataset in sorted(by_dataset):
        days = by_dataset[dataset]
        newest = max(days)
        rows = days[newest]
        out.append({
            "id": f"waking:{dataset}:{newest}",
            "kind": "waking",
            "about": dataset,
            "for_date": newest,
            "resolves": sorted(str(r["at"]) for r in rows),
            "settled_by": "athlete",
        })
    return out


# --- an instrument that stopped, and a zero that should have been an absence --
#
# THE TWO SHAPES A DEAD WEARABLE LEAVES, and they are not one problem with two
# symptoms. A GAP is honest: the record says nothing and every reader already
# treats absence as absence. A FALSE ZERO is a fabricated measurement - it
# averages into weekly steps, `kcal_out` and energy availability exactly as
# though somebody observed it - and the athlete will never report it, because
# from their side nothing looks wrong. They know they lost sleep tracking; they
# have no reason to suspect a zero.
#
# THEY STAY TWO KINDS BECAUSE THEY WANT OPPOSITE GESTURES. A gap is answered by
# an APPEND: the day has no row and one can be added. A false zero is answered
# by a SUPERSEDE: a row exists and is wrong, and appending beside it leaves the
# lie in the record with a correction next to it rather than over it. A consumer
# handed one undifferentiated "these days need attention" list cannot tell which
# it is holding and will reach for the wrong one, so `kind` carries the
# difference. No parallel `remedy` field is emitted: it would co-vary with
# `kind` in every row forever, which is a second definition of one fact.
#
# DAILY ONLY, and that is a boundary rather than a first instalment. A `daily`
# row is supposed to exist for every day, so its absence means something. A
# `sessions` source going quiet is confounded with not training - an athlete who
# rests produces no session, and an engine that read that as an instrument
# failure would ask why the watch stopped every time somebody took a week off.
# The two need different evidence and only the first is derivable from silence.


# Fields where a zero from an instrument means IT SAW NOTHING, not that there
# was nothing to see. Declared, and the declaration is the finding rather than
# a shortcut - see `false_zero_questions` for the measurement that forced it.
#
# A FLOOR, NOT A DEFINITION, the same way `boundary_gate`'s word list is. It
# holds the one field where zero is categorically implausible for a worn
# device: a person wearing a synced wearable does not take zero steps in a
# day. Widening it is a claim about another field and should be argued.
#
# WHY THE OBVIOUS NEIGHBOURS ARE OUT. `active_min` and `distance_km` are
# honestly zero on a rest day, so a question about them would be asking the
# athlete to confirm they had a quiet Tuesday. `kcal_out` is never exactly
# zero even from a dying device - the reporting issue describes it arriving
# near the floor - and separating "near the floor" from "low" needs a
# threshold on a distribution, which is the invented number this module
# refuses.
ZERO_MEANS_UNOBSERVED = frozenset({"steps"})


def _by_source(rows: list[dict], on: date) -> dict[str, list[dict]]:
    """Live daily rows on or before `on`, grouped by the source that wrote
    them, each group in date order.

    PER SOURCE, because every question here is about ONE instrument
    contradicting itself or falling quiet. The canonical view cannot answer
    either: it merges the day's claims into one row, so which instrument said
    what is exactly the fact it resolves away.
    """
    out: dict[str, list[dict]] = {}
    for row in rows:
        source = str(row.get("source") or "").strip()
        when = _as_date(row.get("date"))
        if not source or when is None or when > on:
            continue
        out.setdefault(source, []).append(row)
    for source in out:
        out[source].sort(key=lambda r: str(r.get("date")))
    return out


def false_zero_questions(daily: list[dict], on: date) -> list[dict]:
    """A day a source reported an exact zero it had never reported before.

    THE RULE IS THE SOURCE CONTRADICTING ITSELF, not a threshold on the value
    (G85: no invented number where a principled rule exists). A zero is out of
    family when this source has never written a zero for this field before -
    the record's own history is what decides whether zero is a thing this
    instrument says.

    THE FIELD SET IS DECLARED (`ZERO_MEANS_UNOBSERVED`) AND THAT WAS FORCED BY
    MEASUREMENT, not chosen for convenience. This rule was built first over
    every numeric daily field, on the issue's own reasoning that a field whose
    recent non-zero distribution makes zero implausible could be recognised
    from the distribution alone. Run against the shipped corpus it produced
    FOUR questions and every one was a false positive - three on `pain` and
    one on `sugar_g`, each simply the first ordinary day somebody had no pain
    or ate no sugar - and it produced no true positive anywhere, because no
    corpus record contains the shape this kind exists for.

    A second attempt failed the same way: "the source writes this field on
    every day it appears" separates a wearable's step count from an occasional
    note in principle, and in this corpus `pain` is written on 71 of 71 and 42
    of 42 days, so it separates nothing.

    The conclusion is worth stating because it contradicts the issue: whether
    a zero means NOT OBSERVED or means NONE is a fact about what the field
    means, and no amount of looking at its distribution recovers it. So it is
    declared, with the reasoning beside the register, and kept to the one
    field where the claim is safe.

    ONLY THE FIRST ZERO, and the engine stops there deliberately. Once the
    record shows this source writing zeros for this field, the engine has no
    basis left for calling the next one wrong - it would be arguing with
    evidence it just accepted. Answering the first is what settles the
    interpretation, and superseding it removes the row, so the NEXT zero is
    first again and gets asked about in its turn.

    EXACT ZERO ONLY, AND THAT LEAVES SOMETHING UNCAUGHT. The reporting issue
    describes the dying watch writing a near-floor `kcal_out` beside its zero
    steps, and this rule does not catch it: 1500 is not zero, and deciding it
    is "too low" needs a threshold on a distribution, which is the invented
    number the rest of this module refuses. The zero is detectable because it
    is categorical - the source has never said it - and the floor is not. What
    saves the day in practice is that both arrive together, so the zero raises
    the question and the athlete's answer covers the row; but a day where only
    the floor appears is not derivable here and is not claimed to be.

    ONE QUESTION PER SOURCE, carrying every field that went out of family on
    the day. A dying watch reports its zero steps and its floor `kcal_out` in
    the same breath, and that is one instrument failing once, not two facts.
    The most recent such day wins, for the reason `waking_questions` takes the
    most recent unplaceable day: it is the one the athlete can still remember,
    and it bounds the output by construction rather than by a cap somebody
    could raise.
    """
    fields = sorted(ZERO_MEANS_UNOBSERVED)
    out = []
    for source, rows in sorted(_by_source(daily, on).items()):
        seen_zero: set[str] = set()
        first_zero_days: dict[str, list[str]] = {}
        for row in rows:
            day = str(row.get("date"))
            for field in fields:
                value = row.get(field)
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    continue
                if value != 0:
                    continue
                if field in seen_zero:
                    continue
                seen_zero.add(field)
                first_zero_days.setdefault(day, []).append(field)
        if not first_zero_days:
            continue
        day = max(first_zero_days)
        out.append({
            "id": f"false_zero:daily:{source}:{day}",
            "kind": "false_zero",
            "about": "daily",
            "for_date": day,
            "subject": source,
            "resolves": sorted(first_zero_days[day]),
            "settled_by": "athlete",
        })
    return out


def outage_questions(daily: list[dict], on: date) -> list[dict]:
    """A source that had been contributing and has gone quiet.

    CADENCE IS MEASURED, NEVER ASSUMED. The run of silence has to be longer
    than the longest gap this source has ALREADY shown in this record, so a
    weekly source is not silent after two days and a daily one is. No number
    appears here: the comparison is against the record's own worst case, which
    is the same move `crossings` makes when it asks what the series has done
    before rather than what a constant says it should do.

    SILENCE IS NOT AN INSTRUMENT. A record that never carried a step count is
    never asked why it stopped carrying one - the same refusal the protocol
    advisory makes, where a record with none declared has nothing to be
    missing. Mechanically that falls out of needing gaps to compare against:
    a source seen once has no gap at all.

    TWO PRIOR GAPS, NOT ONE, and this is a distinction in kind rather than a
    magnitude picked to feel safe. With a single prior gap "longer than ever
    before" compares against one observation, which is an anecdote and not a
    cadence: a source seen twice a day apart would be called silent on its
    second quiet day, having never demonstrated a habit to have broken. Two is
    the smallest number of gaps for which "longer than any of them" says
    anything at all.

    ONE QUESTION PER RUN, and per source there is only ever one run that
    matters - the one still open at `on`. A five-day outage is one fact about
    one episode, not five facts, and the discipline this module opens with
    applies here harder than anywhere: the longer somebody is away the more
    days go missing and the more the engine wants to ask, which is precisely
    when a questionnaire is least welcome. A source that has resumed is not
    asked about at all, because the answer would resolve nothing that is still
    open.

    `for_date` is the first silent day and `through` the last, so the run is
    stated rather than left for a client to reconstruct from a count.
    """
    out = []
    for source, rows in sorted(_by_source(daily, on).items()):
        days = sorted({d for r in rows if (d := _as_date(r.get("date")))})
        if len(days) < 3:
            continue
        gaps = [(b - a).days for a, b in zip(days, days[1:])]
        current = (on - days[-1]).days
        if current <= max(gaps):
            continue
        first_silent = days[-1] + timedelta(days=1)
        out.append({
            "id": f"outage:daily:{source}:{first_silent.isoformat()}",
            "kind": "outage",
            "about": "daily",
            "for_date": first_silent.isoformat(),
            "through": on.isoformat(),
            "subject": source,
            "settled_by": "athlete",
        })
    return out
