"""The inference runner: a model reads the record, new knowledge is appended.

This is the ONE place the intelligence layer enters through code rather than
through an agent harness - and it is deliberately fenced:

- OPT-IN: runs only via `vitai infer` with an `[inference]` section in
  vitai.toml. The engine commands (build/validate/status) stay offline.
- APPEND-ONLY OUTPUT: the model's product is lines for data/inferences.jsonl
  (kind/statement/confidence/evidence), schema-validated before a single
  byte is appended. Invalid lines are dropped and reported, never repaired
  silently.
- NEVER IN THE NUMBER PATH: inferences are a projected dataset; no verdict,
  rollup or rate ever reads them.

Backends are pluggable (interface + factory): `claude-cli` shells out to the
Claude Code CLI; `openai-compatible` speaks the /v1/chat/completions shape
(Ollama, LiteLLM, llama.cpp servers, or any hosted endpoint). Both are thin
on purpose - the contract is the prompt + validation, not the transport.
"""

from __future__ import annotations

import json
import subprocess
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from .schema import validate_record

PROMPT = """You are the inference layer of vitai, a personal health coach.
Below is one athlete's current weekly rollup and their recent data. Infer up
to {max_items} NEW pieces of knowledge that are supported by the data shown:
patterns, risks, questions worth asking, or observations. Do not repeat the
prior inferences listed. Do not give medical diagnoses. Do not restate raw
numbers as "insights".

Output STRICTLY one JSON object per line (JSONL), no prose, no markdown
fences, each with exactly these keys:
{{"date":"{today}","kind":"pattern|risk|recommendation|observation|question",
"statement":"...","confidence":0.0-1.0,"model":"{model}",
"evidence":"which dates/datasets support this","note":null}}

=== WEEKLY ROLLUP ===
{rollup}

=== RECENT DAILY LINES (last {n_daily}) ===
{daily}

=== RECENT SESSIONS (last {n_sessions}) ===
{sessions}

=== PRIOR INFERENCES (do not repeat) ===
{prior}
"""


class ModelBackend(Protocol):
    name: str
    def complete(self, prompt: str) -> str: ...


@dataclass
class ClaudeCLIBackend:
    """Shells out to the Claude Code CLI (`claude -p`). Uses the user's own
    authenticated CLI - no key handling here."""
    model: str = ""
    name: str = "claude-cli"

    def complete(self, prompt: str) -> str:
        cmd = ["claude", "-p", prompt, "--output-format", "text"]
        if self.model:
            cmd += ["--model", self.model]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if out.returncode != 0:
            raise RuntimeError(f"claude CLI failed: {out.stderr.strip()[:400]}")
        return out.stdout


@dataclass
class OpenAICompatibleBackend:
    """POSTs /v1/chat/completions - Ollama, llama.cpp server, LiteLLM, etc."""
    base_url: str
    model: str
    api_key: str = ""
    name: str = "openai-compatible"

    def complete(self, prompt: str) -> str:
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }).encode()
        req = urllib.request.Request(
            self.base_url.rstrip("/") + "/v1/chat/completions",
            data=body, headers={"Content-Type": "application/json"})
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        with urllib.request.urlopen(req, timeout=300) as resp:
            payload = json.load(resp)
        return payload["choices"][0]["message"]["content"]


def backend_from_config(inf: dict) -> ModelBackend:
    """Factory: [inference] table from vitai.toml -> backend instance."""
    kind = inf.get("backend", "")
    if kind == "claude-cli":
        return ClaudeCLIBackend(model=inf.get("model", ""))
    if kind == "openai-compatible":
        if not inf.get("base_url") or not inf.get("model"):
            raise ValueError("[inference] openai-compatible needs base_url and model")
        import os
        key = os.environ.get(inf.get("api_key_env", ""), "") if inf.get("api_key_env") else ""
        return OpenAICompatibleBackend(base_url=inf["base_url"],
                                       model=inf["model"], api_key=key)
    raise ValueError(f"unknown [inference] backend {kind!r} "
                     f"(claude-cli | openai-compatible)")


def parse_inferences(text: str, today: str, model_name: str) -> tuple[list[dict], list[str]]:
    """Model output -> (valid records, error strings). Strict, never repairs."""
    valid: list[dict] = []
    errors: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip().strip("`")
        if not line or not line.startswith("{"):
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"line {n}: not JSON ({e})")
            continue
        rec.setdefault("date", today)
        rec.setdefault("model", model_name)
        rec.setdefault("note", None)
        problems = validate_record("inferences", rec)
        if problems:
            errors.append(f"line {n}: " + "; ".join(problems))
        else:
            valid.append(rec)
    return valid, errors


def run_inference(root: Path, backend: ModelBackend, rollup: str,
                  daily: list[dict], sessions: list[dict], prior: list[dict],
                  today: date, max_items: int = 5) -> tuple[list[dict], list[str]]:
    """Build the prompt, call the model, validate. Does NOT append - the
    caller decides (dry-run support)."""
    prompt = PROMPT.format(
        max_items=max_items, today=today.isoformat(),
        model=backend.name, rollup=rollup,
        n_daily=14, daily="\n".join(json.dumps(d) for d in daily[-14:]),
        n_sessions=10, sessions="\n".join(json.dumps(s) for s in sessions[-10:]),
        prior="\n".join(f"- {i['statement']}" for i in prior[-20:]) or "(none)",
    )
    return parse_inferences(backend.complete(prompt), today.isoformat(), backend.name)


def append_inferences(root: Path, records: list[dict]) -> int:
    path = root / "data" / "inferences.jsonl"
    with path.open("a", encoding="utf-8", newline="\n") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return len(records)
