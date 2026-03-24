"""Call logger — appends LLM call records to .harness/logs/calls.jsonl."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _logs_file(base: Path | None = None) -> Path:
    from harness_kit.config import harness_dir
    return harness_dir(base) / "logs" / "calls.jsonl"


def log_call(
    *,
    skill: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    duration: float,
    status: str = "success",
    error: str | None = None,
    inputs: dict[str, Any] | None = None,
    output: str | None = None,
    base: Path | None = None,
) -> None:
    """Append a call record to .harness/logs/calls.jsonl.

    Creates the file (and parent directories) if they don't exist.
    Silently ignores write errors so that logging never breaks the main flow.
    """
    record: dict[str, Any] = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "type": "llm_call",
        "skill": skill,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "duration": round(duration, 3),
        "status": status,
    }
    if error is not None:
        record["error"] = error
    if inputs is not None:
        record["inputs"] = inputs
    if output is not None:
        record["output_preview"] = output[:200] + ("..." if len(output) > 200 else "")

    try:
        log_file = _logs_file(base)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # logging must not break the main flow


def tail_logs(
    n: int = 20,
    base: Path | None = None,
) -> list[dict[str, Any]]:
    """Return the last n call log records."""
    log_file = _logs_file(base)
    if not log_file.exists():
        return []
    lines = log_file.read_text(encoding="utf-8").splitlines()
    records = []
    for line in lines[-n:]:
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def search_logs(
    skill: str | None = None,
    status: str | None = None,
    limit: int = 50,
    base: Path | None = None,
) -> list[dict[str, Any]]:
    """Search call logs with optional filters."""
    log_file = _logs_file(base)
    if not log_file.exists():
        return []
    results: list[dict[str, Any]] = []
    for line in log_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if skill and record.get("skill") != skill:
            continue
        if status and record.get("status") != status:
            continue
        results.append(record)
    return results[-limit:]
