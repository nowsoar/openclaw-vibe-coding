"""Harness health check — analyse skill staleness, success rates, unused assets, schema freshness.

Public API
----------
run_health_check(base, success_threshold, stale_days)
    Returns a HealthReport with issues grouped by severity.

auto_fix(report, base, dry_run)
    Attempts to auto-fix all auto_fixable issues in the report.
    Returns a FixReport.
"""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

DEFAULT_STALE_DAYS = 14
DEFAULT_SUCCESS_THRESHOLD = 0.8  # 80 %


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class HealthIssue:
    severity: str            # "warning" | "critical"
    category: str            # "staleness" | "success_rate" | "unused_asset" | "schema_outdated"
    asset_type: str
    name: str
    message: str
    fix_hint: str = ""
    auto_fixable: bool = False
    extra: dict = field(default_factory=dict)


@dataclass
class HealthReport:
    issues: list[HealthIssue] = field(default_factory=list)
    scanned_skills: int = 0
    scanned_schemas: int = 0
    scanned_assets: int = 0

    @property
    def critical_issues(self) -> list[HealthIssue]:
        return [i for i in self.issues if i.severity == SEVERITY_CRITICAL]

    @property
    def warning_issues(self) -> list[HealthIssue]:
        return [i for i in self.issues if i.severity == SEVERITY_WARNING]

    @property
    def is_healthy(self) -> bool:
        return len(self.critical_issues) == 0

    @property
    def auto_fixable_count(self) -> int:
        return sum(1 for i in self.issues if i.auto_fixable)


@dataclass
class FixResult:
    issue: HealthIssue
    success: bool
    message: str


@dataclass
class FixReport:
    results: list[FixResult] = field(default_factory=list)

    @property
    def fixed_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.success)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_health_check(
    base: Path | None = None,
    success_threshold: float = DEFAULT_SUCCESS_THRESHOLD,
    stale_days: int = DEFAULT_STALE_DAYS,
) -> HealthReport:
    """Run a comprehensive health check on all Harness assets.

    Parameters
    ----------
    base:
        Optional ``.harness/`` root override.
    success_threshold:
        Minimum acceptable success rate (0.0–1.0) for a skill.  Skills with
        fewer than 5 recorded calls are skipped.
    stale_days:
        Number of days since last update before a skill/schema is considered
        stale.

    Returns
    -------
    HealthReport
        Contains a list of HealthIssue items and scan counters.
    """
    from harness_kit.config import harness_dir

    hd = harness_dir(base)
    report = HealthReport()

    _check_skill_staleness(hd, report, stale_days)
    _check_skill_success_rates(hd, report, success_threshold)
    _check_unused_assets(hd, report)
    _check_schema_outdated(hd, report, stale_days)

    return report


def auto_fix(
    report: HealthReport,
    base: Path | None = None,
    dry_run: bool = False,
) -> FixReport:
    """Attempt to auto-fix all auto_fixable issues in *report*.

    Parameters
    ----------
    report:
        A HealthReport returned by :func:`run_health_check`.
    base:
        Optional ``.harness/`` root override.
    dry_run:
        If ``True``, describe what *would* be done without making any changes.

    Returns
    -------
    FixReport
        Results for every auto-fixable issue that was attempted.
    """
    fix_report = FixReport()

    for issue in report.issues:
        if not issue.auto_fixable:
            continue
        result = _try_fix(issue, base=base, dry_run=dry_run)
        fix_report.results.append(result)

    return fix_report


# ---------------------------------------------------------------------------
# Internal check helpers
# ---------------------------------------------------------------------------


def _skill_last_modified(skill_dir: Path) -> datetime | None:
    """Return the mtime of the current skill version file."""
    current_file = skill_dir / "_current"
    if not current_file.exists():
        return None
    version = current_file.read_text(encoding="utf-8").strip()
    ver_file = skill_dir / f"{version}.yaml"
    if not ver_file.exists():
        return None
    return datetime.fromtimestamp(ver_file.stat().st_mtime, tz=timezone.utc)


def _check_skill_staleness(
    hd: Path,
    report: HealthReport,
    stale_days: int,
) -> None:
    """Check if any skill hasn't been updated for more than *stale_days* days."""
    skills_dir = hd / "skills"
    if not skills_dir.exists():
        return

    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(days=stale_days)

    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        name = skill_dir.name
        report.scanned_skills += 1

        last_mod = _skill_last_modified(skill_dir)
        if last_mod is None:
            continue

        if last_mod < cutoff:
            days_ago = (now - last_mod).days
            # Double the threshold → critical; otherwise warning
            severity = (
                SEVERITY_CRITICAL
                if days_ago >= stale_days * 2
                else SEVERITY_WARNING
            )
            report.issues.append(
                HealthIssue(
                    severity=severity,
                    category="staleness",
                    asset_type="skill",
                    name=name,
                    message=(
                        f"Skill '{name}' has not been updated in {days_ago} days "
                        f"(threshold: {stale_days} days)"
                    ),
                    fix_hint=(
                        f"Review and update skill '{name}' to ensure it is still relevant. "
                        f"Run: harnesskit skill show {name}"
                    ),
                    auto_fixable=False,
                    extra={"last_modified": last_mod.isoformat(), "days_ago": days_ago},
                )
            )


def _load_call_logs(hd: Path) -> list[dict[str, Any]]:
    """Load all call log records from ``.harness/logs/calls.jsonl``."""
    log_file = hd / "logs" / "calls.jsonl"
    if not log_file.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in log_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            continue
    return records


def _check_skill_success_rates(
    hd: Path,
    report: HealthReport,
    success_threshold: float,
) -> None:
    """Check if any skill has a success rate below *success_threshold*."""
    records = _load_call_logs(hd)
    if not records:
        return

    skill_total: dict[str, int] = defaultdict(int)
    skill_success: dict[str, int] = defaultdict(int)

    for rec in records:
        skill = rec.get("skill")
        if not skill:
            continue
        skill_total[skill] += 1
        if rec.get("status") == "success":
            skill_success[skill] += 1

    for skill_name, total in skill_total.items():
        if total < 5:
            # Not enough data to draw reliable conclusions
            continue
        success = skill_success[skill_name]
        rate = success / total
        if rate < success_threshold:
            pct = round(rate * 100, 1)
            threshold_pct = round(success_threshold * 100, 1)
            # Below 75 % of threshold → critical
            severity = (
                SEVERITY_CRITICAL
                if rate < success_threshold * 0.75
                else SEVERITY_WARNING
            )
            report.issues.append(
                HealthIssue(
                    severity=severity,
                    category="success_rate",
                    asset_type="skill",
                    name=skill_name,
                    message=(
                        f"Skill '{skill_name}' success rate is {pct}% "
                        f"(threshold: {threshold_pct}%, {total} calls total)"
                    ),
                    fix_hint=(
                        f"Review recent failures for '{skill_name}'. "
                        "Consider updating prompts, rules, or model config."
                    ),
                    auto_fixable=False,
                    extra={
                        "success_rate": round(rate, 4),
                        "total_calls": total,
                        "success_calls": success,
                    },
                )
            )


def _collect_referenced_assets(hd: Path) -> set[tuple[str, str]]:
    """Return a set of (asset_type, name) tuples referenced by any skill or harness."""
    import yaml  # local import — avoids top-level dependency issues in tests

    referenced: set[tuple[str, str]] = set()

    def _scan_dir(yaml_dir: Path) -> None:
        if not yaml_dir.exists():
            return
        for yaml_file in yaml_dir.rglob("*.yaml"):
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue

            # assets section (skills)
            assets = data.get("assets", {})
            if isinstance(assets, dict):
                prompts = assets.get("prompts", {})
                if isinstance(prompts, dict):
                    for ref in prompts.values():
                        if isinstance(ref, str):
                            referenced.add(("prompt", ref.split("@")[0]))
                schemas = assets.get("schemas", [])
                if isinstance(schemas, list):
                    for ref in schemas:
                        if isinstance(ref, str):
                            referenced.add(("schema", ref.split("@")[0]))
                rules = assets.get("rules", [])
                if isinstance(rules, list):
                    for ref in rules:
                        if isinstance(ref, str):
                            referenced.add(("rule", ref.split("@")[0]))
                ctx = assets.get("context")
                if isinstance(ctx, str):
                    referenced.add(("context", ctx.split("@")[0]))

            # harness constraints/rules
            constraints = data.get("constraints", {})
            if isinstance(constraints, dict):
                for ref in constraints.get("rules", []):
                    if isinstance(ref, str):
                        referenced.add(("rule", ref.split("@")[0]))

            # harness → skills list
            for ref in data.get("skills", []):
                if isinstance(ref, str):
                    referenced.add(("skill", ref.split("@")[0]))

    _scan_dir(hd / "skills")
    _scan_dir(hd / "harnesses")
    return referenced


def _check_unused_assets(hd: Path, report: HealthReport) -> None:
    """Check for primitive assets not referenced by any skill or harness."""
    referenced = _collect_referenced_assets(hd)

    for asset_type, subdir in [
        ("prompt", "prompts"),
        ("schema", "schemas"),
        ("context", "contexts"),
        ("rule", "rules"),
    ]:
        asset_dir = hd / subdir
        if not asset_dir.exists():
            continue
        for item in sorted(asset_dir.iterdir()):
            if asset_type == "rule":
                if not item.is_file() or not item.name.endswith(".yaml"):
                    continue
                name = item.stem
            else:
                if not item.is_dir():
                    continue
                name = item.name

            report.scanned_assets += 1
            if (asset_type, name) not in referenced:
                report.issues.append(
                    HealthIssue(
                        severity=SEVERITY_WARNING,
                        category="unused_asset",
                        asset_type=asset_type,
                        name=name,
                        message=(
                            f"{asset_type.capitalize()} '{name}' is not referenced "
                            "by any skill or harness"
                        ),
                        fix_hint=(
                            f"Either reference '{name}' in a skill/harness, or delete it: "
                            f"harnesskit {asset_type} delete {name}"
                        ),
                        auto_fixable=True,
                        extra={"subdir": subdir},
                    )
                )


def _schema_last_modified(schema_dir: Path) -> datetime | None:
    """Return the mtime of the current schema version file."""
    current_file = schema_dir / "_current"
    if not current_file.exists():
        return None
    version = current_file.read_text(encoding="utf-8").strip()
    for ext in (".json", ".yaml"):
        ver_file = schema_dir / f"{version}{ext}"
        if ver_file.exists():
            return datetime.fromtimestamp(ver_file.stat().st_mtime, tz=timezone.utc)
    return None


def _check_schema_outdated(
    hd: Path,
    report: HealthReport,
    stale_days: int,
) -> None:
    """Check if any schema hasn't been updated for more than *stale_days* days."""
    schemas_dir = hd / "schemas"
    if not schemas_dir.exists():
        return

    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(days=stale_days)

    for schema_dir in sorted(schemas_dir.iterdir()):
        if not schema_dir.is_dir():
            continue
        name = schema_dir.name
        report.scanned_schemas += 1

        last_mod = _schema_last_modified(schema_dir)
        if last_mod is None:
            continue

        if last_mod < cutoff:
            days_ago = (now - last_mod).days
            report.issues.append(
                HealthIssue(
                    severity=SEVERITY_WARNING,
                    category="schema_outdated",
                    asset_type="schema",
                    name=name,
                    message=(
                        f"Schema '{name}' has not been updated in {days_ago} days "
                        f"(threshold: {stale_days} days)"
                    ),
                    fix_hint=(
                        f"Review schema '{name}' for correctness and update if needed: "
                        f"harnesskit schema show {name}"
                    ),
                    auto_fixable=False,
                    extra={"last_modified": last_mod.isoformat(), "days_ago": days_ago},
                )
            )


# ---------------------------------------------------------------------------
# Auto-fix helpers
# ---------------------------------------------------------------------------


def _try_fix(
    issue: HealthIssue,
    base: Path | None,
    dry_run: bool,
) -> FixResult:
    """Dispatch to the appropriate fix handler based on *issue.category*."""
    if issue.category == "unused_asset":
        return _fix_unused_asset(issue, base=base, dry_run=dry_run)
    return FixResult(
        issue=issue,
        success=False,
        message=f"No auto-fix handler for category '{issue.category}'",
    )


def _fix_unused_asset(
    issue: HealthIssue,
    base: Path | None,
    dry_run: bool,
) -> FixResult:
    """Delete an unused primitive asset directory (or file for rules)."""
    from harness_kit.config import harness_dir

    hd = harness_dir(base)
    subdir = issue.extra.get("subdir", f"{issue.asset_type}s")
    asset_path: Path

    if issue.asset_type == "rule":
        asset_path = hd / subdir / f"{issue.name}.yaml"
    else:
        asset_path = hd / subdir / issue.name

    if not asset_path.exists():
        return FixResult(
            issue=issue,
            success=False,
            message=f"Path not found: {asset_path}",
        )

    if dry_run:
        return FixResult(
            issue=issue,
            success=True,
            message=f"[dry-run] Would delete: {asset_path}",
        )

    try:
        if asset_path.is_dir():
            shutil.rmtree(asset_path)
        else:
            asset_path.unlink()
        return FixResult(
            issue=issue,
            success=True,
            message=f"Deleted: {asset_path}",
        )
    except Exception as exc:
        return FixResult(
            issue=issue,
            success=False,
            message=f"Failed to delete {asset_path}: {exc}",
        )
