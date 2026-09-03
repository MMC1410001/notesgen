"""Drive the `claude` CLI in headless mode.

Uses the existing Claude Code subscription rather than an API key, so there is
no per-token bill. Deliberately does NOT pass --bare: that flag forces
ANTHROPIC_API_KEY auth and would bypass the subscription entirely.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import time
from dataclasses import dataclass

from . import prompts


class EngineError(RuntimeError):
    pass


@dataclass
class Result:
    text: str
    cost_usd: float = 0.0
    duration_ms: int = 0


def ensure_available() -> str:
    exe = shutil.which("claude")
    if not exe:
        raise EngineError("the `claude` CLI is not on PATH")
    return exe


def call(
    prompt: str,
    *,
    model: str = "sonnet",
    timeout: int = 600,
    attempts: int = 3,
) -> Result:
    exe = ensure_available()
    cmd = [
        exe,
        "-p",
        "--model", model,
        "--output-format", "json",
        "--no-session-persistence",
        # Pure text transformation: no tools, and no chance of the model
        # wandering off to read or write files mid-run.
        "--allowedTools", "",
        "--max-turns", "1",
        "--append-system-prompt", prompts.SYSTEM,
    ]

    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if proc.returncode != 0:
                raise EngineError(
                    f"claude exited {proc.returncode}: {proc.stderr.strip()[:400]}"
                )
            return _parse(proc.stdout)
        except (EngineError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            last = exc
            if attempt == attempts:
                break
            # Usage limits and transient overload both benefit from backing
            # off rather than hammering.
            time.sleep(min(60, 5 * 2 ** (attempt - 1)) + random.uniform(0, 3))

    raise EngineError(f"failed after {attempts} attempts: {last}")


def _parse(stdout: str) -> Result:
    payload = json.loads(stdout)
    if payload.get("is_error"):
        raise EngineError(f"claude reported an error: {str(payload)[:400]}")
    text = payload.get("result") or ""
    if not text.strip():
        raise EngineError("claude returned an empty result")
    return Result(
        text=text.strip(),
        cost_usd=float(payload.get("total_cost_usd") or 0.0),
        duration_ms=int(payload.get("duration_ms") or 0),
    )
