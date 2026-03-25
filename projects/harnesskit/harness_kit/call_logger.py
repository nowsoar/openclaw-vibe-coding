"""Call logger — appends LLM call records to .harness/logs/calls.jsonl."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _logs_file(base: Path | None = None) -> Path:
    from harness_kit.config import harness_dir
    return harness_dir(base) / "logs" / "calls.jsonl"


def _parse_since(since: str | None) -> datetime | None:
    """Parse a human-readable duration string into a UTC cutoff datetime.

    Supports: ``Nd`` (days), ``Nh`` (hours), ``Nm`` (minutes), ``Ns`` (seconds).
    Examples: ``"1d"``, ``"7d"``, ``"2h"``, ``"30m"``.

    Returns ``None`` when *since* is ``None`` or empty.
    """
    if not since:
        return None
    m = re.fullmatch(r"(\d+)([dhms])", since.strip().lower())
    if not m:
        raise ValueError(
            f"Invalid --since value {since!r}. Use a number followed by d/h/m/s (e.g. '1d', '2h')."
        )
    amount, unit = int(m.group(1)), m.group(2)
    delta = {
        "d": timedelta(days=amount),
        "h": timedelta(hours=amount),
        "m": timedelta(minutes=amount),
        "s": timedelta(seconds=amount),
    }[unit]
    return datetime.now(tz=timezone.utc) - delta


def log_call(
    *,
    skill: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    duration: float,
    cost: float | None = None,
    status: str = "success",
    error: str | None = None,
    inputs: dict[str, Any] | None = None,
    output: str | None = None,
    violations: list[dict[str, Any]] | None = None,
    base: Path | None = None,
) -> None:
    """Append a call record to .harness/logs/calls.jsonl.

    Creates the file (and parent directories) if they don't exist.
    Silently ignores write errors so that logging never breaks the main flow.

    Parameters
    ----------
    cost:
        Estimated USD cost for this call (input + output tokens at model rates).
    violations:
        List of rule violation dicts, each with keys: rule, type, matches, fix_hint.
        Included when any hard rules are triggered (both strict and lenient modes).
    """
    record: dict[str, Any] = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "type": "llm_call",
        "skill": skill,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost": round(cost, 6) if cost is not None else None,
        "duration": round(duration, 3),
        "status": status,
    }
    if error is not None:
        record["error"] = error
    if inputs is not None:
        record["inputs"] = inputs
    if output is not None:
        record["output_preview"] = output[:200] + ("..." if len(output) > 200 else "")
    if violations is not None:
        record["violations"] = violations
        record["violation_count"] = len(violations)

    try:
        log_file = _logs_file(base)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # logging must not break the main flow


def tail_logs(
    n: int = 20,
    since: str | None = None,
    base: Path | None = None,
) -> list[dict[str, Any]]:
    """Return the last *n* call log records, optionally filtered by *since*.

    Parameters
    ----------
    n:
        Maximum number of records to return (applied after time filter).
    since:
        Duration string such as ``"1d"`` or ``"2h"``.  Only records whose
        *timestamp* is within this window are returned.
    """
    log_file = _logs_file(base)
    if not log_file.exists():
        return []
    cutoff = _parse_since(since)
    records: list[dict[str, Any]] = []
    for line in log_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if cutoff is not None:
            ts_str = rec.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts < cutoff:
                    continue
            except ValueError:
                continue
        records.append(rec)
    return records[-n:]


def search_logs(
    skill: str | None = None,
    status: str | None = None,
    since: str | None = None,
    limit: int = 50,
    base: Path | None = None,
) -> list[dict[str, Any]]:
    """Search call logs with optional filters.

    Parameters
    ----------
    skill:
        Only return records whose ``skill`` field matches this value exactly.
    status:
        Only return records whose ``status`` field matches (``"success"``/``"error"``).
    since:
        Duration string such as ``"1d"`` or ``"2h"``.  Only records within
        this time window are returned.
    limit:
        Maximum number of matching records to return (most-recent first).
    """
    log_file = _logs_file(base)
    if not log_file.exists():
        return []
    cutoff = _parse_since(since)
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
        if cutoff is not None:
            ts_str = record.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts < cutoff:
                    continue
            except ValueError:
                continue
        results.append(record)
    return results[-limit:]


def export_logs(
    since: str | None = None,
    skill: str | None = None,
    fmt: str = "csv",
    base: Path | None = None,
) -> str:
    """Export call logs as CSV or JSON Lines string.

    Parameters
    ----------
    since:
        Duration string such as ``"7d"``.
    skill:
        Filter by skill name.
    fmt:
        ``"csv"`` (default) or ``"jsonl"``.
    """
    records = search_logs(skill=skill, since=since, limit=100_000, base=base)

    if fmt == "jsonl":
        return "\n".join(json.dumps(r, ensure_ascii=False) for r in records)

    # CSV
    if not records:
        return ""
    fieldnames = [
        "timestamp", "type", "skill", "model",
        "input_tokens", "output_tokens", "total_tokens",
        "cost", "duration", "status", "error",
        "violation_count",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for rec in records:
        writer.writerow({k: rec.get(k, "") for k in fieldnames})
    return buf.getvalue()


def violation_stats(
    base: Path | None = None,
) -> dict[str, int]:
    """Return a mapping of rule_name → total violation count across all call logs."""
    log_file = _logs_file(base)
    if not log_file.exists():
        return {}
    counts: dict[str, int] = {}
    for line in log_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        for v in record.get("violations") or []:
            rule = v.get("rule", "unknown")
            counts[rule] = counts.get(rule, 0) + 1
    return counts
