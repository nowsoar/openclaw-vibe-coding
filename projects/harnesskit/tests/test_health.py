"""Tests for Phase 6.5: Harness 健康检查 — health check & auto-fix."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from harness_kit import health as health_mod
from harness_kit.cli import app
from harness_kit.config import init_harness

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


def _write_call_log(base: Path, skill: str = "test-skill", status: str = "success") -> None:
    log_file = base / ".harness" / "logs" / "calls.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "type": "llm_call",
        "skill": skill,
        "model": "gpt-4o",
        "input_tokens": 200,
        "output_tokens": 100,
        "status": status,
        "cost": 0.005,
        "duration": 1.0,
    }
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def _make_skill(base: Path, name: str, days_old: int = 0) -> None:
    """Create a minimal skill directory with a version file aged by *days_old* days."""
    skill_dir = base / ".harness" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    ver_file = skill_dir / "v0.1.0.yaml"
    ver_file.write_text(
        yaml.dump({"name": name, "version": "v0.1.0", "description": "test"}),
        encoding="utf-8",
    )
    (skill_dir / "_current").write_text("v0.1.0", encoding="utf-8")
    if days_old > 0:
        # Back-date the mtime
        import os
        past = (datetime.now() - timedelta(days=days_old)).timestamp()
        os.utime(ver_file, (past, past))


def _make_schema(base: Path, name: str, days_old: int = 0) -> None:
    """Create a minimal schema directory."""
    schema_dir = base / ".harness" / "schemas" / name
    schema_dir.mkdir(parents=True, exist_ok=True)
    ver_file = schema_dir / "v0.1.0.json"
    ver_file.write_text(
        json.dumps({"type": "object", "properties": {}, "required": []}),
        encoding="utf-8",
    )
    (schema_dir / "_current").write_text("v0.1.0", encoding="utf-8")
    if days_old > 0:
        import os
        past = (datetime.now() - timedelta(days=days_old)).timestamp()
        os.utime(ver_file, (past, past))


def _make_prompt(base: Path, name: str) -> None:
    prompt_dir = base / ".harness" / "prompts" / name
    prompt_dir.mkdir(parents=True, exist_ok=True)
    ver_file = prompt_dir / "v0.1.0.yaml"
    ver_file.write_text(
        yaml.dump({"name": name, "version": "v0.1.0", "content": "Test prompt."}),
        encoding="utf-8",
    )
    (prompt_dir / "_current").write_text("v0.1.0", encoding="utf-8")


def _make_rule(base: Path, name: str) -> None:
    rule_file = base / ".harness" / "rules" / f"{name}.yaml"
    rule_file.parent.mkdir(parents=True, exist_ok=True)
    rule_file.write_text(
        yaml.dump({"name": name, "type": "hard", "description": "test rule"}),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Unit tests: run_health_check — empty workspace
# ---------------------------------------------------------------------------


class TestHealthCheckEmpty:
    def test_empty_workspace_no_issues(self, workspace: Path) -> None:
        report = health_mod.run_health_check(base=workspace)
        assert report.issues == []
        assert report.is_healthy is True

    def test_empty_workspace_zero_scanned(self, workspace: Path) -> None:
        report = health_mod.run_health_check(base=workspace)
        assert report.scanned_skills == 0
        assert report.scanned_schemas == 0
        assert report.scanned_assets == 0


# ---------------------------------------------------------------------------
# Unit tests: skill staleness check
# ---------------------------------------------------------------------------


class TestStalenessCheck:
    def test_fresh_skill_no_issue(self, workspace: Path) -> None:
        _make_skill(workspace, "fresh-skill", days_old=0)
        report = health_mod.run_health_check(base=workspace, stale_days=14)
        stale = [i for i in report.issues if i.category == "staleness"]
        assert len(stale) == 0

    def test_stale_skill_warning(self, workspace: Path) -> None:
        _make_skill(workspace, "old-skill", days_old=20)
        report = health_mod.run_health_check(base=workspace, stale_days=14)
        stale = [i for i in report.issues if i.category == "staleness"]
        assert len(stale) == 1
        assert stale[0].name == "old-skill"

    def test_very_stale_skill_is_critical(self, workspace: Path) -> None:
        _make_skill(workspace, "ancient-skill", days_old=30)
        report = health_mod.run_health_check(base=workspace, stale_days=14)
        stale = [i for i in report.issues if i.category == "staleness"]
        assert len(stale) == 1
        assert stale[0].severity == health_mod.SEVERITY_CRITICAL

    def test_moderately_stale_skill_is_warning(self, workspace: Path) -> None:
        _make_skill(workspace, "slightly-old", days_old=20)
        report = health_mod.run_health_check(base=workspace, stale_days=14)
        stale = [i for i in report.issues if i.category == "staleness"]
        assert len(stale) == 1
        assert stale[0].severity == health_mod.SEVERITY_WARNING

    def test_scanned_skills_counter(self, workspace: Path) -> None:
        _make_skill(workspace, "skill-a", days_old=0)
        _make_skill(workspace, "skill-b", days_old=0)
        report = health_mod.run_health_check(base=workspace)
        assert report.scanned_skills == 2


# ---------------------------------------------------------------------------
# Unit tests: success rate check
# ---------------------------------------------------------------------------


class TestSuccessRateCheck:
    def test_no_logs_no_issue(self, workspace: Path) -> None:
        report = health_mod.run_health_check(base=workspace, success_threshold=0.8)
        sr_issues = [i for i in report.issues if i.category == "success_rate"]
        assert len(sr_issues) == 0

    def test_low_call_count_skipped(self, workspace: Path) -> None:
        # Only 4 calls — below minimum of 5
        for _ in range(4):
            _write_call_log(workspace, skill="rare-skill", status="error")
        report = health_mod.run_health_check(base=workspace, success_threshold=0.8)
        sr_issues = [i for i in report.issues if i.category == "success_rate"]
        assert len(sr_issues) == 0

    def test_low_success_rate_warning(self, workspace: Path) -> None:
        # 3 success, 5 failure → 37.5% < 80%
        for _ in range(3):
            _write_call_log(workspace, skill="bad-skill", status="success")
        for _ in range(5):
            _write_call_log(workspace, skill="bad-skill", status="error")
        report = health_mod.run_health_check(base=workspace, success_threshold=0.8)
        sr_issues = [i for i in report.issues if i.category == "success_rate"]
        assert len(sr_issues) == 1
        assert sr_issues[0].name == "bad-skill"

    def test_very_low_success_rate_critical(self, workspace: Path) -> None:
        # 1 success, 9 failure → 10% << 80%
        _write_call_log(workspace, skill="broken-skill", status="success")
        for _ in range(9):
            _write_call_log(workspace, skill="broken-skill", status="error")
        report = health_mod.run_health_check(base=workspace, success_threshold=0.8)
        sr_issues = [i for i in report.issues if i.category == "success_rate"]
        assert len(sr_issues) == 1
        assert sr_issues[0].severity == health_mod.SEVERITY_CRITICAL

    def test_high_success_rate_no_issue(self, workspace: Path) -> None:
        for _ in range(8):
            _write_call_log(workspace, skill="good-skill", status="success")
        for _ in range(2):
            _write_call_log(workspace, skill="good-skill", status="error")
        report = health_mod.run_health_check(base=workspace, success_threshold=0.8)
        sr_issues = [i for i in report.issues if i.category == "success_rate"]
        # 80% == threshold → no issue
        assert len(sr_issues) == 0


# ---------------------------------------------------------------------------
# Unit tests: unused asset check
# ---------------------------------------------------------------------------


class TestUnusedAssetCheck:
    def test_unreferenced_prompt_flagged(self, workspace: Path) -> None:
        _make_prompt(workspace, "orphan-prompt")
        report = health_mod.run_health_check(base=workspace)
        unused = [i for i in report.issues if i.category == "unused_asset"]
        assert any(i.name == "orphan-prompt" for i in unused)

    def test_unreferenced_rule_flagged(self, workspace: Path) -> None:
        _make_rule(workspace, "orphan-rule")
        report = health_mod.run_health_check(base=workspace)
        unused = [i for i in report.issues if i.category == "unused_asset"]
        assert any(i.name == "orphan-rule" for i in unused)

    def test_referenced_prompt_not_flagged(self, workspace: Path) -> None:
        _make_prompt(workspace, "used-prompt")
        _make_skill(workspace, "my-skill", days_old=0)
        # Write skill YAML that references the prompt
        skill_dir = workspace / ".harness" / "skills" / "my-skill"
        (skill_dir / "v0.1.0.yaml").write_text(
            yaml.dump({
                "name": "my-skill",
                "version": "v0.1.0",
                "assets": {"prompts": {"system": "used-prompt@v0.1.0"}},
            }),
            encoding="utf-8",
        )
        report = health_mod.run_health_check(base=workspace)
        unused = [i for i in report.issues if i.category == "unused_asset"]
        assert not any(i.name == "used-prompt" for i in unused)

    def test_unused_asset_is_auto_fixable(self, workspace: Path) -> None:
        _make_prompt(workspace, "deletable-prompt")
        report = health_mod.run_health_check(base=workspace)
        unused = [i for i in report.issues if i.category == "unused_asset"]
        assert len(unused) > 0
        assert all(i.auto_fixable for i in unused)

    def test_scanned_assets_counter(self, workspace: Path) -> None:
        _make_prompt(workspace, "p1")
        _make_prompt(workspace, "p2")
        _make_rule(workspace, "r1")
        report = health_mod.run_health_check(base=workspace)
        assert report.scanned_assets >= 3


# ---------------------------------------------------------------------------
# Unit tests: schema outdated check
# ---------------------------------------------------------------------------


class TestSchemaOutdatedCheck:
    def test_fresh_schema_no_issue(self, workspace: Path) -> None:
        _make_schema(workspace, "fresh-schema", days_old=0)
        report = health_mod.run_health_check(base=workspace, stale_days=14)
        outdated = [i for i in report.issues if i.category == "schema_outdated"]
        assert len(outdated) == 0

    def test_old_schema_warning(self, workspace: Path) -> None:
        _make_schema(workspace, "old-schema", days_old=20)
        report = health_mod.run_health_check(base=workspace, stale_days=14)
        outdated = [i for i in report.issues if i.category == "schema_outdated"]
        assert len(outdated) == 1
        assert outdated[0].name == "old-schema"
        assert outdated[0].severity == health_mod.SEVERITY_WARNING

    def test_scanned_schemas_counter(self, workspace: Path) -> None:
        _make_schema(workspace, "s1")
        _make_schema(workspace, "s2")
        report = health_mod.run_health_check(base=workspace)
        assert report.scanned_schemas == 2


# ---------------------------------------------------------------------------
# Unit tests: auto_fix
# ---------------------------------------------------------------------------


class TestAutoFix:
    def test_fix_removes_unused_prompt(self, workspace: Path) -> None:
        _make_prompt(workspace, "dead-prompt")
        prompt_dir = workspace / ".harness" / "prompts" / "dead-prompt"
        assert prompt_dir.exists()

        report = health_mod.run_health_check(base=workspace)
        fix_report = health_mod.auto_fix(report, base=workspace, dry_run=False)

        assert fix_report.fixed_count >= 1
        assert not prompt_dir.exists()

    def test_fix_removes_unused_rule(self, workspace: Path) -> None:
        _make_rule(workspace, "dead-rule")
        rule_file = workspace / ".harness" / "rules" / "dead-rule.yaml"
        assert rule_file.exists()

        report = health_mod.run_health_check(base=workspace)
        fix_report = health_mod.auto_fix(report, base=workspace, dry_run=False)

        assert fix_report.fixed_count >= 1
        assert not rule_file.exists()

    def test_dry_run_does_not_delete(self, workspace: Path) -> None:
        _make_prompt(workspace, "keep-prompt")
        prompt_dir = workspace / ".harness" / "prompts" / "keep-prompt"
        assert prompt_dir.exists()

        report = health_mod.run_health_check(base=workspace)
        fix_report = health_mod.auto_fix(report, base=workspace, dry_run=True)

        # Directory should still be there
        assert prompt_dir.exists()
        # But results should show success (dry-run simulates success)
        assert fix_report.fixed_count >= 1

    def test_non_fixable_issues_skipped(self, workspace: Path) -> None:
        _make_skill(workspace, "stale-skill", days_old=30)
        report = health_mod.run_health_check(base=workspace, stale_days=14)
        # stale issues are not auto_fixable
        fix_report = health_mod.auto_fix(report, base=workspace, dry_run=False)
        assert fix_report.fixed_count == 0
        assert len(fix_report.results) == 0


# ---------------------------------------------------------------------------
# Unit tests: HealthReport properties
# ---------------------------------------------------------------------------


class TestHealthReportProperties:
    def test_is_healthy_no_critical(self, workspace: Path) -> None:
        report = health_mod.HealthReport()
        report.issues.append(health_mod.HealthIssue(
            severity=health_mod.SEVERITY_WARNING,
            category="unused_asset",
            asset_type="prompt",
            name="x",
            message="test",
        ))
        assert report.is_healthy is True

    def test_is_unhealthy_with_critical(self, workspace: Path) -> None:
        report = health_mod.HealthReport()
        report.issues.append(health_mod.HealthIssue(
            severity=health_mod.SEVERITY_CRITICAL,
            category="staleness",
            asset_type="skill",
            name="x",
            message="test",
        ))
        assert report.is_healthy is False

    def test_auto_fixable_count(self, workspace: Path) -> None:
        report = health_mod.HealthReport()
        report.issues.append(health_mod.HealthIssue(
            severity=health_mod.SEVERITY_WARNING,
            category="unused_asset",
            asset_type="prompt",
            name="x",
            message="test",
            auto_fixable=True,
        ))
        report.issues.append(health_mod.HealthIssue(
            severity=health_mod.SEVERITY_WARNING,
            category="staleness",
            asset_type="skill",
            name="y",
            message="test",
            auto_fixable=False,
        ))
        assert report.auto_fixable_count == 1


# ---------------------------------------------------------------------------
# CLI integration tests: health check
# ---------------------------------------------------------------------------


class TestHealthCheckCli:
    def test_check_healthy_workspace(self, workspace: Path) -> None:
        result = runner.invoke(app, ["health", "check"])
        assert result.exit_code == 0
        assert "healthy" in result.output.lower()

    def test_check_with_stale_skill_exits_nonzero_for_critical(self, workspace: Path) -> None:
        # 30 days old → critical (2× default threshold of 14)
        _make_skill(workspace, "ancient", days_old=30)
        result = runner.invoke(app, ["health", "check", "--stale-days", "14"])
        assert result.exit_code != 0
        assert "ancient" in result.output

    def test_check_shows_warning_issues(self, workspace: Path) -> None:
        _make_skill(workspace, "slightly-old", days_old=20)
        result = runner.invoke(app, ["health", "check", "--stale-days", "14"])
        # Warning only → exit 0 (not critical)
        assert "slightly-old" in result.output

    def test_check_shows_unused_asset(self, workspace: Path) -> None:
        _make_prompt(workspace, "unused-prompt")
        result = runner.invoke(app, ["health", "check"])
        assert result.exit_code == 0
        assert "unused-prompt" in result.output

    def test_check_shows_auto_fixable_hint(self, workspace: Path) -> None:
        _make_prompt(workspace, "deletable")
        result = runner.invoke(app, ["health", "check"])
        assert "harnesskit health fix" in result.output

    def test_check_not_initialized(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["health", "check"])
        assert result.exit_code != 0

    def test_check_scanned_summary_shown(self, workspace: Path) -> None:
        _make_skill(workspace, "my-skill")
        result = runner.invoke(app, ["health", "check"])
        assert "Scanned" in result.output


# ---------------------------------------------------------------------------
# CLI integration tests: health fix
# ---------------------------------------------------------------------------


class TestHealthFixCli:
    def test_fix_no_fixable_issues(self, workspace: Path) -> None:
        result = runner.invoke(app, ["health", "fix", "--yes"])
        assert result.exit_code == 0
        assert "No auto-fixable issues" in result.output

    def test_fix_removes_unused_prompt_with_yes(self, workspace: Path) -> None:
        _make_prompt(workspace, "orphan")
        prompt_dir = workspace / ".harness" / "prompts" / "orphan"
        assert prompt_dir.exists()
        result = runner.invoke(app, ["health", "fix", "--yes"])
        assert result.exit_code == 0
        assert not prompt_dir.exists()

    def test_fix_dry_run_does_not_delete(self, workspace: Path) -> None:
        _make_prompt(workspace, "keepme")
        prompt_dir = workspace / ".harness" / "prompts" / "keepme"
        result = runner.invoke(app, ["health", "fix", "--dry-run"])
        assert result.exit_code == 0
        assert "no changes were made" in result.output.lower()
        assert prompt_dir.exists()

    def test_fix_shows_fix_report(self, workspace: Path) -> None:
        _make_prompt(workspace, "orphan2")
        result = runner.invoke(app, ["health", "fix", "--yes"])
        assert result.exit_code == 0
        assert "Fix Report" in result.output

    def test_fix_not_initialized(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["health", "fix", "--yes"])
        assert result.exit_code != 0
