"""Stats dashboard — aggregates call-log data for a skill or harness.

Public API
----------
skill_stats(target, since, base)
    Returns a structured dict with call count, success rate, duration,
    token distribution, and error type distribution.

bar_chart(buckets, width, total)
    Returns a list of Rich-renderable strings representing a simple
    ASCII bar chart row.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_since(since: str | None) -> datetime | None:
    if not since:
        return None
    m = re.fullmatch(r"(\d+)([dhms])", since.strip().lower())
    if not m:
        raise ValueError(
            f"Invalid --since value {since!r}. Use a number followed by d/h/m/s."
        )
    amount, unit = int(m.group(1)), m.group(2)
    delta = {
        "d": timedelta(days=amount),
        "h": timedelta(hours=amount),
        "m": timedelta(minutes=amount),
        "s": timedelta(seconds=amount),
    }[unit]
    return datetime.now(tz=timezone.utc) - delta


def _load_records(
    target: str | None,
    since: str | None,
    base: Path | None,
) -> list[dict[str, Any]]:
    """Load matching call-log records from .harness/logs/calls.jsonl.

    Reads the file line-by-line to avoid loading the entire log into memory.
    """
    import json

    from harness_kit.config import harness_dir

    log_file = harness_dir(base) / "logs" / "calls.jsonl"
    if not log_file.exists():
        return []

    cutoff = _parse_since(since)
    records: list[dict[str, Any]] = []

    with log_file.open(encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except Exception:
                continue

            # Filter by target name (skill field)
            if target and rec.get("skill") != target:
                continue

            # Filter by time window
            if cutoff is not None:
                ts_str = rec.get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts < cutoff:
                        continue
                except ValueError:
                    continue

            records.append(rec)

    return records


# ---------------------------------------------------------------------------
# Token bucket helpers
# ---------------------------------------------------------------------------

_TOKEN_BUCKETS = [
    (0, 100, "0–100"),
    (101, 250, "101–250"),
    (251, 500, "251–500"),
    (501, 1000, "501–1K"),
    (1001, 2000, "1K–2K"),
    (2001, 5000, "2K–5K"),
    (5001, 10000, "5K–10K"),
    (10001, float("inf"), "10K+"),
]


def _bucket_tokens(total_tokens: int) -> str:
    for lo, hi, label in _TOKEN_BUCKETS:
        if lo <= total_tokens <= hi:
            return label
    return "10K+"


# ---------------------------------------------------------------------------
# Duration bucket helpers
# ---------------------------------------------------------------------------

_DURATION_BUCKETS = [
    (0, 1, "0–1s"),
    (1, 3, "1–3s"),
    (3, 5, "3–5s"),
    (5, 10, "5–10s"),
    (10, 30, "10–30s"),
    (30, float("inf"), "30s+"),
]


def _bucket_duration(duration: float) -> str:
    for lo, hi, label in _DURATION_BUCKETS:
        if lo <= duration < hi:
            return label
    return "30s+"


# ---------------------------------------------------------------------------
# Main stats function
# ---------------------------------------------------------------------------

def skill_stats(
    target: str | None = None,
    since: str | None = None,
    base: Path | None = None,
) -> dict[str, Any]:
    """Aggregate call-log statistics for *target* (skill or harness name).

    Parameters
    ----------
    target:
        The skill (or harness) name to filter by.  Pass ``None`` to
        aggregate across **all** calls.
    since:
        Time-window filter such as ``"7d"``, ``"24h"``.  ``None`` means
        all time.
    base:
        Optional path override for the ``.harness/`` root.

    Returns
    -------
    dict with keys:
    - target: str | None
    - since: str | None
    - total_calls: int
    - success_calls: int
    - error_calls: int
    - success_rate: float  (0.0–1.0)
    - avg_duration: float | None  (seconds)
    - min_duration: float | None
    - max_duration: float | None
    - avg_input_tokens: float | None
    - avg_output_tokens: float | None
    - avg_total_tokens: float | None
    - total_tokens: int
    - total_cost: float
    - avg_cost: float | None
    - by_status: dict[str, int]
    - token_buckets: dict[str, int]   (total-token distribution)
    - duration_buckets: dict[str, int]
    - error_types: dict[str, int]     (error message → count)
    - models_used: dict[str, int]     (model → call count)
    """
    records = _load_records(target=target, since=since, base=base)

    total_calls = len(records)
    success_calls = 0
    error_calls = 0
    durations: list[float] = []
    input_tokens_list: list[int] = []
    output_tokens_list: list[int] = []
    total_tokens_sum = 0
    total_cost = 0.0
    costs: list[float] = []

    by_status: dict[str, int] = defaultdict(int)
    token_buckets: dict[str, int] = defaultdict(int)
    duration_buckets: dict[str, int] = defaultdict(int)
    error_types: dict[str, int] = defaultdict(int)
    models_used: dict[str, int] = defaultdict(int)

    for rec in records:
        status = rec.get("status", "unknown")
        by_status[status] += 1
        if status == "success":
            success_calls += 1
        else:
            error_calls += 1
            err = rec.get("error") or status
            # Normalize: truncate long error messages
            err_key = err[:80] if isinstance(err, str) else str(err)[:80]
            error_types[err_key] += 1

        dur = rec.get("duration")
        if dur is not None:
            try:
                dur = float(dur)
                durations.append(dur)
                duration_buckets[_bucket_duration(dur)] += 1
            except (TypeError, ValueError):
                pass

        in_tok = rec.get("input_tokens", 0) or 0
        out_tok = rec.get("output_tokens", 0) or 0
        tot_tok = rec.get("total_tokens", 0) or (in_tok + out_tok)
        input_tokens_list.append(in_tok)
        output_tokens_list.append(out_tok)
        total_tokens_sum += tot_tok
        token_buckets[_bucket_tokens(tot_tok)] += 1

        cost = rec.get("cost")
        if cost is not None:
            try:
                cost = float(cost)
                total_cost += cost
                costs.append(cost)
            except (TypeError, ValueError):
                pass

        model = rec.get("model", "unknown")
        models_used[model] += 1

    success_rate = (success_calls / total_calls) if total_calls > 0 else 0.0
    avg_duration = (sum(durations) / len(durations)) if durations else None
    min_duration = min(durations) if durations else None
    max_duration = max(durations) if durations else None
    avg_input = (sum(input_tokens_list) / len(input_tokens_list)) if input_tokens_list else None
    avg_output = (sum(output_tokens_list) / len(output_tokens_list)) if output_tokens_list else None
    avg_total = (total_tokens_sum / total_calls) if total_calls > 0 else None
    avg_cost = (total_cost / len(costs)) if costs else None

    # Sort buckets in logical order
    def _ordered(buckets: dict[str, int], order: list[str]) -> dict[str, int]:
        result = {k: buckets.get(k, 0) for k in order if k in buckets}
        # Add any unexpected buckets at the end
        for k in buckets:
            if k not in result:
                result[k] = buckets[k]
        return result

    tok_order = [b[2] for b in _TOKEN_BUCKETS]
    dur_order = [b[2] for b in _DURATION_BUCKETS]

    return {
        "target": target,
        "since": since,
        "total_calls": total_calls,
        "success_calls": success_calls,
        "error_calls": error_calls,
        "success_rate": round(success_rate, 4),
        "avg_duration": round(avg_duration, 3) if avg_duration is not None else None,
        "min_duration": round(min_duration, 3) if min_duration is not None else None,
        "max_duration": round(max_duration, 3) if max_duration is not None else None,
        "avg_input_tokens": round(avg_input, 1) if avg_input is not None else None,
        "avg_output_tokens": round(avg_output, 1) if avg_output is not None else None,
        "avg_total_tokens": round(avg_total, 1) if avg_total is not None else None,
        "total_tokens": total_tokens_sum,
        "total_cost": round(total_cost, 6),
        "avg_cost": round(avg_cost, 6) if avg_cost is not None else None,
        "by_status": dict(sorted(by_status.items())),
        "token_buckets": _ordered(dict(token_buckets), tok_order),
        "duration_buckets": _ordered(dict(duration_buckets), dur_order),
        "error_types": dict(sorted(error_types.items(), key=lambda x: -x[1])),
        "models_used": dict(sorted(models_used.items(), key=lambda x: -x[1])),
    }


# ---------------------------------------------------------------------------
# Bar chart helper for CLI rendering
# ---------------------------------------------------------------------------

def bar_chart_rows(
    buckets: dict[str, int],
    bar_width: int = 30,
    color: str = "cyan",
) -> list[tuple[str, int, str]]:
    """Return renderable rows for a horizontal bar chart.

    Each row is a tuple of (label, count, bar_string).
    The bar_string is a Rich-markup string using block characters.
    """
    if not buckets:
        return []
    max_val = max(buckets.values()) or 1
    rows = []
    for label, count in buckets.items():
        filled = int((count / max_val) * bar_width)
        bar = f"[{color}]{'█' * filled}[/{color}][dim]{'░' * (bar_width - filled)}[/dim]"
        rows.append((label, count, bar))
    return rows
