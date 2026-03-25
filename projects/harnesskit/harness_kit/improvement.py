"""Improvement Flywheel — record, track, and report Harness/Skill improvements.

Public API
----------
log_improvement(skill, issue, root_cause, fix, before_version, after_version,
                eval_improvement, base)
    Append one improvement record to ``.harness/improvements/{skill}.jsonl``.

get_history(skill, since, base)
    Return a list of improvement records for *skill*.

improvement_report(period, base)
    Aggregate improvement records across all skills for a given period.
    Returns a structured dict suitable for CLI rendering.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _improvements_dir(base: Path | None) -> Path:
    from harness_kit.config import harness_dir
    return harness_dir(base) / "improvements"


def _parse_period(period: str) -> datetime:
    """Convert a period string (day/week/month or Nd/Nh) to a UTC cutoff datetime."""
    period = period.strip().lower()
    # Named periods
    named = {"day": 1, "week": 7, "month": 30}
    if period in named:
        return datetime.now(tz=timezone.utc) - timedelta(days=named[period])
    # Relative: 3d, 12h, etc.
    m = re.fullmatch(r"(\d+)([dhm])", period)
    if m:
        amount, unit = int(m.group(1)), m.group(2)
        delta = {"d": timedelta(days=amount), "h": timedelta(hours=amount), "m": timedelta(minutes=amount)}[unit]
        return datetime.now(tz=timezone.utc) - delta
    raise ValueError(
        f"Invalid period {period!r}. Use 'day', 'week', 'month', or a value like '7d', '24h'."
    )


def _load_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except Exception:
                continue
    return records


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_improvement(
    *,
    skill: str,
    issue: str,
    root_cause: str,
    fix: str,
    before_version: str,
    after_version: str,
    eval_improvement: str = "",
    base: Path | None = None,
) -> dict[str, Any]:
    """Append one improvement record to ``.harness/improvements/{skill}.jsonl``.

    Returns the written record.
    """
    record: dict[str, Any] = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "type": "improvement",
        "skill": skill,
        "issue": issue,
        "root_cause": root_cause,
        "fix": fix,
        "before_version": before_version,
        "after_version": after_version,
        "eval_improvement": eval_improvement,
    }

    imp_dir = _improvements_dir(base)
    imp_dir.mkdir(parents=True, exist_ok=True)
    log_file = imp_dir / f"{skill}.jsonl"
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


def get_history(
    skill: str,
    since: str | None = None,
    base: Path | None = None,
) -> list[dict[str, Any]]:
    """Return improvement records for *skill*, optionally filtered by *since*.

    Parameters
    ----------
    skill:
        Skill name.
    since:
        Optional time filter such as ``"7d"``, ``"24h"``, ``"week"``.
    base:
        Optional ``.harness/`` root override.
    """
    imp_dir = _improvements_dir(base)
    log_file = imp_dir / f"{skill}.jsonl"
    records = _load_file(log_file)

    if since is not None:
        cutoff = _parse_period(since)
        filtered = []
        for rec in records:
            ts_str = rec.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts >= cutoff:
                    filtered.append(rec)
            except ValueError:
                filtered.append(rec)
        records = filtered

    # Most-recent first
    return list(reversed(records))


def list_skills_with_improvements(base: Path | None = None) -> list[str]:
    """Return names of all skills that have any improvement records."""
    imp_dir = _improvements_dir(base)
    if not imp_dir.exists():
        return []
    return sorted(p.stem for p in imp_dir.glob("*.jsonl"))


def improvement_report(
    period: str = "week",
    base: Path | None = None,
) -> dict[str, Any]:
    """Aggregate improvement records across all skills for a given *period*.

    Returns
    -------
    dict with keys:
    - period: str
    - cutoff: str        (ISO8601 UTC timestamp)
    - total: int         (total improvements logged)
    - by_skill: dict[str, int]
    - records: list[dict]   (all matching records, most-recent first)
    - eval_gains: list[str] (non-empty eval_improvement strings)
    """
    cutoff = _parse_period(period)
    imp_dir = _improvements_dir(base)

    all_records: list[dict[str, Any]] = []
    if imp_dir.exists():
        for jl_file in sorted(imp_dir.glob("*.jsonl")):
            all_records.extend(_load_file(jl_file))

    # Filter by cutoff
    filtered: list[dict[str, Any]] = []
    for rec in all_records:
        ts_str = rec.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts >= cutoff:
                filtered.append(rec)
        except ValueError:
            filtered.append(rec)

    # Aggregate
    by_skill: dict[str, int] = defaultdict(int)
    eval_gains: list[str] = []
    for rec in filtered:
        by_skill[rec.get("skill", "unknown")] += 1
        gain = rec.get("eval_improvement", "")
        if gain:
            eval_gains.append(gain)

    # Sort most-recent first
    def _ts(r: dict) -> str:
        return r.get("timestamp", "")

    sorted_records = sorted(filtered, key=_ts, reverse=True)

    return {
        "period": period,
        "cutoff": cutoff.isoformat(),
        "total": len(filtered),
        "by_skill": dict(sorted(by_skill.items(), key=lambda x: -x[1])),
        "records": sorted_records,
        "eval_gains": eval_gains,
    }
