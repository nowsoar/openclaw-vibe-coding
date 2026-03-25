"""Cost tracking module — estimates and aggregates LLM call costs.

Pricing is stored in .harness/config.yaml under ``model_pricing``.
Built-in defaults cover the most common models; users can override via
``harnesskit cost set-price``.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Built-in model pricing table (USD per 1K tokens, input/output)
# ---------------------------------------------------------------------------

DEFAULT_MODEL_PRICING: dict[str, dict[str, float]] = {
    # OpenAI
    "gpt-4o":              {"input": 0.0025, "output": 0.010},
    "gpt-4o-mini":         {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo":         {"input": 0.010,  "output": 0.030},
    "gpt-4":               {"input": 0.030,  "output": 0.060},
    "gpt-3.5-turbo":       {"input": 0.0005, "output": 0.0015},
    # Anthropic Claude
    "claude-3-5-sonnet":        {"input": 0.003,  "output": 0.015},
    "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
    "claude-3-opus":            {"input": 0.015,  "output": 0.075},
    "claude-3-opus-20240229":   {"input": 0.015,  "output": 0.075},
    "claude-3-haiku":           {"input": 0.00025, "output": 0.00125},
    "claude-3-haiku-20240307":  {"input": 0.00025, "output": 0.00125},
    "claude-3-5-haiku":         {"input": 0.0008,  "output": 0.004},
    # DeepSeek
    "deepseek-v3":         {"input": 0.00027, "output": 0.0011},
    "deepseek-chat":       {"input": 0.00027, "output": 0.0011},
    "deepseek-r1":         {"input": 0.00055, "output": 0.00219},
    # Gemini
    "gemini-1.5-pro":      {"input": 0.00125, "output": 0.005},
    "gemini-1.5-flash":    {"input": 0.000075, "output": 0.0003},
    "gemini-2.0-flash":    {"input": 0.0001,  "output": 0.0004},
}


def _logs_file(base: Path | None = None) -> Path:
    from harness_kit.config import harness_dir
    return harness_dir(base) / "logs" / "calls.jsonl"


def _parse_since(since: str | None) -> datetime | None:
    if not since:
        return None
    m = re.fullmatch(r"(\d+)([dhms])", since.strip().lower())
    if not m:
        raise ValueError(
            f"Invalid --since value {since!r}. Use a number followed by d/h/m/s."
        )
    amount, unit = int(m.group(1)), m.group(2)
    delta = {"d": timedelta(days=amount), "h": timedelta(hours=amount),
             "m": timedelta(minutes=amount), "s": timedelta(seconds=amount)}[unit]
    return datetime.now(tz=timezone.utc) - delta


def get_model_prices(base: Path | None = None) -> dict[str, dict[str, float]]:
    """Return merged pricing: built-ins overridden by user config."""
    try:
        from harness_kit.config import read_config
        cfg = read_config(base)
        user_pricing: dict[str, Any] = cfg.get("model_pricing") or {}
    except Exception:
        user_pricing = {}
    merged = {k: dict(v) for k, v in DEFAULT_MODEL_PRICING.items()}
    for model, prices in user_pricing.items():
        if isinstance(prices, dict):
            merged[model] = {
                "input": float(prices.get("input", 0.0)),
                "output": float(prices.get("output", 0.0)),
            }
    return merged


def set_model_price(
    model: str,
    input_per_1k: float,
    output_per_1k: float,
    base: Path | None = None,
) -> None:
    """Persist a custom model price to .harness/config.yaml."""
    from harness_kit.config import read_config, write_config
    cfg = read_config(base)
    pricing = cfg.get("model_pricing") or {}
    pricing[model] = {"input": round(input_per_1k, 8), "output": round(output_per_1k, 8)}
    cfg["model_pricing"] = pricing
    write_config(cfg, base)


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    base: Path | None = None,
) -> float | None:
    """Return USD cost estimate, or None if model not in pricing table."""
    prices = get_model_prices(base)
    # Try exact match first, then case-insensitive prefix match
    key = model.strip().lower()
    rate = None
    for k, v in prices.items():
        if k.lower() == key:
            rate = v
            break
    if rate is None:
        # Fuzzy: check if model starts with a known key prefix (e.g. gpt-4o-2024...)
        for k, v in prices.items():
            if key.startswith(k.lower()):
                rate = v
                break
    if rate is None:
        return None
    cost = (input_tokens / 1000.0) * rate["input"] + (output_tokens / 1000.0) * rate["output"]
    return round(cost, 8)


def _load_records(
    since: str | None = None,
    base: Path | None = None,
) -> list[dict[str, Any]]:
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
    return records


def cost_report(
    since: str | None = "30d",
    base: Path | None = None,
) -> dict[str, Any]:
    """Aggregate cost data from call logs.

    Returns a dict with:
    - total_cost: float
    - total_calls: int
    - total_tokens: int
    - by_skill: {skill: {cost, calls, tokens}}
    - by_model: {model: {cost, calls, tokens}}
    - most_expensive_call: dict | None
    - daily_breakdown: {date_str: cost}
    """
    records = _load_records(since=since, base=base)

    total_cost = 0.0
    total_calls = 0
    total_tokens = 0
    by_skill: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    daily: dict[str, float] = {}
    most_expensive: dict[str, Any] | None = None

    for rec in records:
        cost_val = rec.get("cost")
        if cost_val is None:
            # Attempt to estimate on-the-fly (for old records without cost)
            cost_val = estimate_cost(
                rec.get("model", ""),
                rec.get("input_tokens", 0),
                rec.get("output_tokens", 0),
                base=base,
            ) or 0.0

        tokens = rec.get("total_tokens", 0) or (
            rec.get("input_tokens", 0) + rec.get("output_tokens", 0)
        )
        skill = rec.get("skill", "unknown")
        model = rec.get("model", "unknown")
        ts = rec.get("timestamp", "")
        date_str = ts[:10] if ts else "unknown"

        total_cost += cost_val
        total_calls += 1
        total_tokens += tokens

        # by_skill
        if skill not in by_skill:
            by_skill[skill] = {"cost": 0.0, "calls": 0, "tokens": 0}
        by_skill[skill]["cost"] += cost_val
        by_skill[skill]["calls"] += 1
        by_skill[skill]["tokens"] += tokens

        # by_model
        if model not in by_model:
            by_model[model] = {"cost": 0.0, "calls": 0, "tokens": 0}
        by_model[model]["cost"] += cost_val
        by_model[model]["calls"] += 1
        by_model[model]["tokens"] += tokens

        # daily
        daily[date_str] = daily.get(date_str, 0.0) + cost_val

        # most expensive
        if most_expensive is None or cost_val > (most_expensive.get("cost") or 0.0):
            most_expensive = {
                "cost": cost_val,
                "skill": skill,
                "model": model,
                "timestamp": ts,
                "input_tokens": rec.get("input_tokens", 0),
                "output_tokens": rec.get("output_tokens", 0),
            }

    # Round accumulated floats for display stability
    for g in by_skill.values():
        g["cost"] = round(g["cost"], 6)
    for g in by_model.values():
        g["cost"] = round(g["cost"], 6)

    return {
        "total_cost": round(total_cost, 6),
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "by_skill": by_skill,
        "by_model": by_model,
        "most_expensive_call": most_expensive,
        "daily_breakdown": dict(sorted(daily.items())),
        "since": since,
    }


def check_cost_alert(
    model: str,
    input_tokens: int,
    output_tokens: int,
    threshold: float | None = None,
    base: Path | None = None,
) -> tuple[bool, float | None]:
    """Return (alert_triggered, cost).

    alert_triggered is True if the estimated cost exceeds *threshold*.
    If threshold is None, checks config for ``cost_alert.per_call``.
    """
    try:
        from harness_kit.config import read_config
        cfg = read_config(base)
        alert_cfg = cfg.get("cost_alert") or {}
        if threshold is None:
            threshold = alert_cfg.get("per_call")
    except Exception:
        pass

    cost = estimate_cost(model, input_tokens, output_tokens, base=base)
    if cost is None or threshold is None:
        return False, cost
    return cost > threshold, cost


def daily_cost_alert(
    base: Path | None = None,
) -> tuple[bool, float]:
    """Check whether today's total cost exceeds the daily alert threshold.

    Returns (alert_triggered, today_cost).
    """
    try:
        from harness_kit.config import read_config
        cfg = read_config(base)
        threshold = (cfg.get("cost_alert") or {}).get("per_day")
    except Exception:
        threshold = None

    today_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    report = cost_report(since="1d", base=base)
    today_cost = report["daily_breakdown"].get(today_str, 0.0)
    if threshold is None:
        return False, today_cost
    return today_cost > threshold, today_cost
