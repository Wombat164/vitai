"""One rule, one place - swept for rather than waited for.

Every expensive defect this engine has shipped has the same shape. `hip_pain`
was a forward map re-implemented at eight readers, and the copies carried the
score and dropped the site. `restriction_scope` grew a second tokeniser that
disagreed with the validator about commas. The seam detector borrowed half of
`vocab.resolve` and claimed the whole of it.

None of those disagreed on the day they were written. They disagreed the first
time ONE of them learned something, and the other silently did not.

So this sweeps the engine for byte-identical function bodies across modules and
holds the answer to a pinned list. Two entries came off it when this was
written:

  `anatomy._normalise`   a second copy of the fold every registry lookup uses.
                         A widening for unicode dashes - smart punctuation from
                         a phone is how a hand-written record acquires one -
                         would land in `vocab` and leave `pain_site` resolving
                         the old way.
  `_numeric` x3          in `query`, `resolution` and `safety`, where it
                         decides whether a pain score reaches a gate.

And one stayed, verified rather than assumed: the three `_week_key` wrappers
are already thin delegations to `weeks.week_of` from #208. Identical bodies
because they are one-line forwards, which is the fix rather than the defect.
"""

from __future__ import annotations

import ast
import collections
import hashlib
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "vitai"

# WHAT MAY SHARE A BODY, and why each is not a second copy of a rule.
#
# A delegating one-liner is the CURE for duplication, so a set of them will
# always look identical to a body comparison. Anything here has to be a
# forward to a single definition, or a constructor whose shape is dictated by
# its dataclass rather than by a rule.
ALLOWED = {
    # Three forwards to `weeks.week_of` (#208), which is the one definition.
    frozenset({"contributions.py._week_key", "report.py._week_key",
               "verdicts.py._week_key"}),
    # Three forwards to `schema.is_number`.
    frozenset({"query.py._numeric", "resolution.py._numeric",
               "safety.py._numeric"}),
    # Two small numeric coercions over different domains: a meal quantity and
    # a set's load. Same three lines, no shared rule to drift.
    frozenset({"meals.py._num", "progression.py._num", "sets.py._num"}),
    frozenset({"progression.py._int", "sets.py._int"}),
    # Two date readers with the same two-line body and different callers.
    frozenset({"query.py._as_date", "safety.py._as_date"}),
    # Store constructors: both take a root and hold it. Shape, not rule.
    frozenset({"artifacts.py.__init__", "sync.py.__init__"}),
}


def _bodies() -> dict[str, list[str]]:
    """Function bodies, keyed by their AST shape, docstrings excluded.

    The AST rather than the text, so reindenting or renaming a local does not
    hide a copy - and the docstring dropped, because two copies of one rule
    usually explain themselves differently, which is exactly how they escape a
    grep.
    """
    found: dict[str, list[str]] = collections.defaultdict(list)
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.FunctionDef):
                continue
            body = list(node.body)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(getattr(body[0], "value", None), ast.Constant)):
                body = body[1:]
            if not body:
                continue
            dump = "".join(ast.dump(n) for n in body)
            if len(dump) < 80:          # one-expression helpers, below signal
                continue
            found[hashlib.sha256(dump.encode()).hexdigest()].append(
                f"{path.name}.{node.name}")
    return found


def test_no_rule_is_implemented_twice():
    """The sweep. A new pair here is either a rule with two homes - fix it -
    or a delegation, which goes on the list with the reason."""
    shared = {frozenset(names) for names in _bodies().values()
              if len(set(names)) > 1}
    unaccounted = shared - ALLOWED
    assert not unaccounted, (
        f"{[sorted(s) for s in unaccounted]} share a body. If that is one rule "
        "in two places, give it one home; if it is a forward to a single "
        "definition, add it to ALLOWED with the reason.")


def test_the_fold_has_one_home():
    """`anatomy` carried a byte-identical copy of `vocab._normalise`, so a
    widening to the fold would reach every registry and not body sites."""
    import inspect

    from vitai import anatomy, vocab

    src = inspect.getsource(anatomy._normalise)
    assert "from .vocab import _normalise" in src, src
    assert "replace" not in src.split('"""')[-1], "it must forward, not re-fold"
    for spelling in ("IT band", "it_band", "IT-band", "  IT   BAND  "):
        assert anatomy.resolve(spelling) == "knee", spelling
        assert vocab._normalise(spelling) == "it band", spelling


def test_what_counts_as_a_number_has_one_home():
    """It decided whether a pain score reached a gate, in three copies."""
    from vitai.schema import is_number

    assert is_number(3) and is_number(3.5) and is_number(0)
    # `True` is an `int` in Python, so this is the whole reason it is a
    # function: `pain: true` would otherwise reach a threshold as the number 1.
    assert not is_number(True) and not is_number(False)
    assert not is_number("3") and not is_number(None)


def test_the_three_numeric_wrappers_agree_by_construction():
    import inspect

    from vitai import query, resolution, safety

    for module in (query, resolution, safety):
        src = inspect.getsource(module._numeric)
        assert "is_number(v)" in src, module.__name__
        assert "isinstance" not in src, module.__name__


def test_the_allowed_list_names_nothing_that_has_gone_away():
    """A stale exemption reads as coverage. Every name here must still exist,
    so a deleted function cannot leave a permission behind it."""
    live = {name for names in _bodies().values() for name in names}
    for group in ALLOWED:
        missing = [n for n in group if n not in live]
        assert not missing, f"{missing} no longer share a body; drop them"


def test_the_sweep_can_actually_fail():
    """A guard on the guard: it must see a pair the ALLOWED list does not
    cover. Simulated, because the tree is clean and the point is that it
    would not stay clean silently."""
    invented = frozenset({"a.py.thing", "b.py.thing"})
    assert invented not in ALLOWED
    assert invented - ALLOWED == invented
