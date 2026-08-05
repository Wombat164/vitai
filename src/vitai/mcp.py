"""An MCP adapter over `vitai.api`. A second harness, never a second surface.

#158 rung 5, and the position it restates rather than revisits: **MCP is a
derived third, not a close second.** The LSP precedent is that the winning
implementations are libraries with thin protocol adapters rather than
protocol-first designs. So `vitai.api` is the surface, the CLI is a harness
over it, and this is another harness over the same thing.

What it buys: an off-the-shelf agent can attach without being taught this
repo's internals. That was consumption mode 1, and it worked until now only by
an agent reading the JSONL directly and reaching into private module
attributes, every one of which will move.

THE TOOLS ARE DERIVED FROM THE API, not listed beside it. `TOOLS` names
methods; the description of each is the first line of that method's own
docstring, and a name that does not resolve on `Vitai` raises at import. So
the adapter structurally cannot expose a capability the API lacks, which is
the acceptance criterion, and it cannot document one differently either.

STDLIB ONLY, like everything else here. MCP's stdio transport is
newline-delimited JSON-RPC 2.0, which is a few dozen lines; taking a
dependency to avoid writing them would cost more than it saved.

Nothing on stdout except protocol. A stray print corrupts the stream, so
diagnostics go to stderr.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .api import Vitai, schema
from .db import DERIVED_TABLES
from .schema import KEYS

PROTOCOL = "2024-11-05"

# Every tool, as (method on `Vitai`, JSON-schema properties, required names).
# `None` as the method means a module-level function of the same name.
#
# Read first, then write, in the order #158 asks for. Nothing here computes:
# each entry is a call into the API and a JSON dump of what came back.
TOOLS: dict[str, dict] = {
    "situation": {
        "method": "situation",
        "properties": {
            "on": {"type": "string",
                   "description": "valid-time viewpoint, ISO date"},
            "recent": {"type": "integer",
                       "description": "how many recent sessions to carry"},
        },
    },
    "schema": {
        "method": None,
        "properties": {},
    },
    "validate": {
        "method": "validate",
        "properties": {},
    },
    "status": {
        "method": "status",
        "properties": {"on": {"type": "string"}},
    },
    "day": {
        "method": "day",
        "properties": {"on": {"type": "string"}},
        "required": ["on"],
    },
    "window": {
        "method": "window",
        "properties": {"days": {"type": "integer"},
                       "on": {"type": "string"}},
    },
    "goals": {
        "method": "goals",
        "properties": {},
    },
    # The read path an agent would otherwise re-derive. Without it the only
    # way to see a dataset through this adapter was to read the JSONL and
    # apply `supersedes` by hand, which is the nine lines that deleted a row
    # and its own correction together (#258). An adapter that leaves the
    # correction rule to the caller has handed out the one part of this
    # engine that is easy to get wrong and quiet about being wrong.
    "dataset": {
        "method": "dataset",
        "properties": {
            # The enum comes from the engine, so the tool describes its own
            # legal values and a wrong name is refused by the caller's own
            # schema check rather than by a KeyError after the fact. The CLI
            # gets this from argparse `choices`; an agent should not be the
            # surface that has to guess.
            "name": {"type": "string", "enum": sorted(KEYS),
                     "description": "which dataset, e.g. weight or sessions"},
        },
        "required": ["name"],
    },
    # The read model's tables, by the name the contract gives them (#267).
    # `best_efforts` had no public path at all, so an agent's only routes were
    # a private attribute or a direct query against a table the contract
    # exists to insulate it from - and #257 was the same failure three weeks
    # earlier, where the consumer took the second and kept a stale copy.
    "derived": {
        "method": "derived",
        "properties": {
            "name": {"type": "string", "enum": sorted(DERIVED_TABLES),
                     "description": "which derived table, e.g. best_efforts"},
        },
        "required": ["name"],
    },
    "safety": {
        "method": "safety",
        "properties": {"on": {"type": "string"}},
    },
    "claim": {
        "method": "claim",
        "properties": {
            "dataset": {"type": "string"},
            "values": {"type": "object",
                       "description": "the quantities stated, by field name"},
            "said": {"type": "string",
                     "description": "the athlete's own words, verbatim"},
            "read_by": {"type": "string",
                        "enum": ["athlete", "model", "human-other"]},
        },
        "required": ["dataset", "values"],
    },
    "said": {
        "method": "said",
        "properties": {
            "text": {"type": "string"},
            "kind": {"type": "string"},
            "about": {"type": "string"},
        },
        "required": ["text"],
    },
}

# Fails at IMPORT if a tool names something the API does not have. A adapter
# that could name a missing capability is one that will, silently, the first
# time a method is renamed.
for _name, _spec in TOOLS.items():
    _m = _spec["method"]
    if _m is not None and not hasattr(Vitai, _m):
        raise AttributeError(
            f"MCP tool {_name!r} names Vitai.{_m}, which does not exist. The "
            "adapter exposes nothing the API lacks, so this is the adapter "
            "being wrong rather than the API being incomplete.")


def _describe(spec: dict) -> str:
    """The method's OWN first docstring line, so the two cannot drift."""
    method = spec["method"]
    doc = (schema if method is None else getattr(Vitai, method)).__doc__ or ""
    return doc.strip().splitlines()[0] if doc.strip() else ""


def tool_list() -> list[dict]:
    return [{
        "name": name,
        "description": _describe(spec),
        "inputSchema": {
            "type": "object",
            "properties": spec["properties"],
            "required": spec.get("required", []),
        },
    } for name, spec in TOOLS.items()]


def call(root: Path, name: str, arguments: dict) -> object:
    """Run one tool. Raises with the engine's own sentence on refusal."""
    spec = TOOLS.get(name)
    if spec is None:
        raise KeyError(f"no such tool {name!r}; one of {sorted(TOOLS)}")
    args = dict(arguments or {})
    # The declared schema is the WHOLE surface, enforced here rather than
    # advertised and hoped for. `inputSchema` is advisory to the client: a
    # caller that ignores it used to have every remaining parameter of the
    # underlying method available, so `claim` accepted `corrects` - the
    # destructive retire path - which the tool deliberately does not offer.
    # An adapter whose real surface is wider than its described one is one
    # nobody can audit from its description, which is the same defect the
    # import-time method check exists to prevent, from the other side.
    unknown = sorted(set(args) - set(spec["properties"]))
    if unknown:
        raise KeyError(
            f"tool {name!r} takes {sorted(spec['properties'])}, got unexpected "
            f"{unknown}. If a capability belongs on this tool it is added to "
            f"TOOLS where it can be seen, never reached through the call")
    if spec["method"] is None:
        return schema()
    # The VIEWPOINT goes to the constructor as well as the call, or a brief
    # answers as today inside a document labelled with another date.
    on = args.pop("on", None) if name in ("situation", "status") else None
    engine = Vitai(root, on=on)
    return getattr(engine, spec["method"])(**args)


def _reply(rid, result=None, error=None) -> None:
    msg = {"jsonrpc": "2.0", "id": rid}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def serve(root: Path, stdin=None, stdout=None) -> int:
    """Newline-delimited JSON-RPC 2.0 on stdio, until the stream closes."""
    src = stdin or sys.stdin
    for line in src:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            _reply(None, error={"code": -32700, "message": f"parse error: {e}"})
            continue
        rid, method = msg.get("id"), msg.get("method")
        params = msg.get("params") or {}
        try:
            if method == "initialize":
                _reply(rid, {
                    "protocolVersion": PROTOCOL,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "vitai", "version": schema()["engine"]},
                })
            elif method == "tools/list":
                _reply(rid, {"tools": tool_list()})
            elif method == "tools/call":
                out = call(root, params.get("name"),
                           params.get("arguments") or {})
                # Text content, because the caller is a model: a JSON string it
                # can read beats a shape it has to be taught.
                _reply(rid, {"content": [{
                    "type": "text",
                    "text": json.dumps(out, indent=2, sort_keys=True,
                                       default=str),
                }]})
            elif method in ("notifications/initialized", "initialized"):
                continue          # a notification: no id, no reply
            elif rid is not None:
                _reply(rid, error={"code": -32601,
                                   "message": f"no such method {method!r}"})
        except Exception as e:  # noqa: BLE001 - a protocol reply, not a crash
            # The ENGINE's sentence, relayed. An agent can act on a sentence;
            # a code has to be interpreted, and every interpreter differs.
            _reply(rid, error={"code": -32000,
                               "message": f"{type(e).__name__}: {e}"})
    return 0
