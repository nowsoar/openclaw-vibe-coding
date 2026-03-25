"""Tests for Phase 6.4: 改进飞轮核心 — Improvement Flywheel."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness_kit import improvement as improve_mod
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


def _write_improvement(base: Path, **overrides) -> dict:
    """Write a single improvement record directly to disk (test helper)."""
    record = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "type": "improvement",
        "skill": "test-skill",
        "issue": "LLM hallucinated a function",
        "root_cause": "Missing no-hallucination rule",
        "fix": "Added no-hallucination hard rule",
        "before_version": "v0.1.0",
        "after_version": "v0.1.1",
        "eval_improvement": "+8%",
    }
    record.update(overrides)
    imp_dir = base / ".harness" / "improvements"
    imp_dir.mkdir(parents=True, exist_ok=True)
    skill = record["skill"]
    log_file = imp_dir / f"{skill}.jsonl"
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record


# ===========================================================================
# Unit tests: log_improvement
# ===========================================================================


class TestLogImprovement:
    def test_creates_jsonl_file(self, workspace: Path) -> None:
        improve_mod.log_improvement(
            skill="my-skill",
            issue="Bad output",
            root_cause="Prompt ambiguity",
            fix="Clarified prompt",
            before_version="v0.1.0",
            after_version="v0.1.1",
            base=workspace,
        )
        log_file = workspace / ".harness" / "improvements" / "my-skill.jsonl"
        assert log_file.exists()

    def test_record_fields_are_correct(self, workspace: Path) -> None:
        rec = improve_mod.log_improvement(
            skill="my-skill",
            issue="Bad output",
            root_cause="Prompt ambiguity",
            fix="Clarified prompt",
            before_version="v0.1.0",
            after_version="v0.1.1",
            eval_improvement="+15%",
            base=workspace,
        )
        assert rec["type"] == "improvement"
        assert rec["skill"] == "my-skill"
        assert rec["issue"] == "Bad output"
        assert rec["root_cause"] == "Prompt ambiguity"
        assert rec["fix"] == "Clarified prompt"
        assert rec["before_version"] == "v0.1.0"
        assert rec["after_version"] == "v0.1.1"
        assert rec["eval_improvement"] == "+15%"
        assert "timestamp" in rec

    def test_appends_multiple_records(self, workspace: Path) -> None:
        for i in range(3):
            improve_mod.log_improvement(
                skill="my-skill",
                issue=f"issue {i}",
                root_cause="cause",
                fix="fix",
                before_version=f"v0.{i}.0",
                after_version=f"v0.{i}.1",
                base=workspace,
            )
        log_file = workspace / ".harness" / "improvements" / "my-skill.jsonl"
        lines = [l for l in log_file.read_text().splitlines() if l.strip()]
        assert len(lines) == 3

    def test_empty_eval_improvement_defaults_empty_string(self, workspace: Path) -> None:
        rec = improve_mod.log_improvement(
            skill="x",
            issue="i",
            root_cause="r",
            fix="f",
            before_version="v0.1.0",
            after_version="v0.1.1",
            base=workspace,
        )
        assert rec["eval_improvement"] == ""


# ===========================================================================
# Unit tests: get_history
# ===========================================================================


class TestGetHistory:
    def test_empty_returns_empty_list(self, workspace: Path) -> None:
        result = improve_mod.get_history("nonexistent-skill", base=workspace)
        assert result == []

    def test_returns_records_most_recent_first(self, workspace: Path) -> None:
        _write_improvement(workspace, skill="sk", issue="first", before_version="v0.1.0", after_version="v0.1.1")
        _write_improvement(workspace, skill="sk", issue="second", before_version="v0.1.1", after_version="v0.1.2")
        records = improve_mod.get_history("sk", base=workspace)
        assert len(records) == 2
        assert records[0]["issue"] == "second"   # most recent first
        assert records[1]["issue"] == "first"

    def test_returns_all_fields(self, workspace: Path) -> None:
        _write_improvement(workspace, skill="sk", eval_improvement="+20%")
        records = improve_mod.get_history("sk", base=workspace)
        rec = records[0]
        assert rec["type"] == "improvement"
        assert rec["eval_improvement"] == "+20%"

    def test_records_isolated_per_skill(self, workspace: Path) -> None:
        _write_improvement(workspace, skill="skill-a")
        _write_improvement(workspace, skill="skill-b")
        assert len(improve_mod.get_history("skill-a", base=workspace)) == 1
        assert len(improve_mod.get_history("skill-b", base=workspace)) == 1


# ===========================================================================
# Unit tests: list_skills_with_improvements
# ===========================================================================


class TestListSkills:
    def test_empty_when_no_improvements(self, workspace: Path) -> None:
        assert improve_mod.list_skills_with_improvements(base=workspace) == []

    def test_returns_skill_names(self, workspace: Path) -> None:
        _write_improvement(workspace, skill="alpha")
        _write_improvement(workspace, skill="beta")
        names = improve_mod.list_skills_with_improvements(base=workspace)
        assert "alpha" in names
        assert "beta" in names


# ===========================================================================
# Unit tests: improvement_report
# ===========================================================================


class TestImprovementReport:
    def test_empty_report(self, workspace: Path) -> None:
        data = improve_mod.improvement_report(period="week", base=workspace)
        assert data["total"] == 0
        assert data["by_skill"] == {}
        assert data["records"] == []
        assert data["eval_gains"] == []

    def test_total_count(self, workspace: Path) -> None:
        _write_improvement(workspace, skill="s1", eval_improvement="+5%")
        _write_improvement(workspace, skill="s1", eval_improvement="+10%")
        _write_improvement(workspace, skill="s2")
        data = improve_mod.improvement_report(period="week", base=workspace)
        assert data["total"] == 3
        assert data["by_skill"]["s1"] == 2
        assert data["by_skill"]["s2"] == 1

    def test_eval_gains_only_non_empty(self, workspace: Path) -> None:
        _write_improvement(workspace, skill="s", eval_improvement="+12%")
        _write_improvement(workspace, skill="s", eval_improvement="")
        data = improve_mod.improvement_report(period="week", base=workspace)
        assert data["eval_gains"] == ["+12%"]

    def test_period_day(self, workspace: Path) -> None:
        _write_improvement(workspace, skill="s")
        data = improve_mod.improvement_report(period="day", base=workspace)
        assert data["total"] == 1

    def test_period_month(self, workspace: Path) -> None:
        _write_improvement(workspace, skill="s")
        data = improve_mod.improvement_report(period="month", base=workspace)
        assert data["total"] == 1

    def test_records_most_recent_first(self, workspace: Path) -> None:
        _write_improvement(workspace, skill="s", issue="first")
        _write_improvement(workspace, skill="s", issue="second")
        data = improve_mod.improvement_report(period="week", base=workspace)
        assert data["records"][0]["issue"] == "second"

    def test_invalid_period_raises(self, workspace: Path) -> None:
        with pytest.raises(ValueError, match="Invalid period"):
            improve_mod.improvement_report(period="fortnightly", base=workspace)


# ===========================================================================
# CLI integration tests
# ===========================================================================


class TestImproveLogCLI:
    def test_log_creates_record(self, workspace: Path) -> None:
        result = runner.invoke(
            app,
            [
                "improve", "log", "my-skill",
                "--issue", "Hallucinated API",
                "--root-cause", "No hallucination rule",
                "--fix", "Added no-hallucination rule",
                "--before", "v0.1.0",
                "--after", "v0.1.1",
                "--eval", "+12%",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Improvement logged" in result.output
        assert "my-skill" in result.output

        log_file = workspace / ".harness" / "improvements" / "my-skill.jsonl"
        assert log_file.exists()
        rec = json.loads(log_file.read_text().strip())
        assert rec["skill"] == "my-skill"
        assert rec["eval_improvement"] == "+12%"

    def test_log_shows_versions(self, workspace: Path) -> None:
        result = runner.invoke(
            app,
            [
                "improve", "log", "sk",
                "--issue", "issue",
                "--root-cause", "cause",
                "--fix", "fix",
                "--before", "v0.2.0",
                "--after", "v0.2.1",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "v0.2.0" in result.output
        assert "v0.2.1" in result.output

    def test_log_without_eval_succeeds(self, workspace: Path) -> None:
        result = runner.invoke(
            app,
            [
                "improve", "log", "sk",
                "--issue", "i",
                "--root-cause", "r",
                "--fix", "f",
                "--before", "v0.1.0",
                "--after", "v0.1.1",
            ],
        )
        assert result.exit_code == 0, result.output


class TestImproveHistoryCLI:
    def test_history_empty(self, workspace: Path) -> None:
        result = runner.invoke(app, ["improve", "history", "no-skill"])
        assert result.exit_code == 0
        assert "No improvement records" in result.output

    def test_history_shows_records(self, workspace: Path) -> None:
        _write_improvement(workspace, skill="sk", issue="old issue")
        result = runner.invoke(app, ["improve", "history", "sk"])
        assert result.exit_code == 0
        assert "old issue" in result.output
        assert "v0.1.0" in result.output

    def test_history_shows_eval_gain(self, workspace: Path) -> None:
        _write_improvement(workspace, skill="sk", eval_improvement="+25%")
        result = runner.invoke(app, ["improve", "history", "sk"])
        assert result.exit_code == 0
        assert "+25%" in result.output

    def test_history_limit(self, workspace: Path) -> None:
        for i in range(5):
            _write_improvement(workspace, skill="sk", issue=f"issue {i}")
        result = runner.invoke(app, ["improve", "history", "sk", "--limit", "2"])
        assert result.exit_code == 0
        assert "more record(s)" in result.output


class TestImproveReportCLI:
    def test_report_empty(self, workspace: Path) -> None:
        result = runner.invoke(app, ["improve", "report", "--period", "week"])
        assert result.exit_code == 0
        assert "No improvements" in result.output

    def test_report_with_data(self, workspace: Path) -> None:
        _write_improvement(workspace, skill="my-skill", eval_improvement="+18%")
        result = runner.invoke(app, ["improve", "report", "--period", "week"])
        assert result.exit_code == 0
        assert "Improvement Report" in result.output
        assert "my-skill" in result.output
        assert "+18%" in result.output

    def test_report_shows_total(self, workspace: Path) -> None:
        _write_improvement(workspace, skill="s1")
        _write_improvement(workspace, skill="s2")
        result = runner.invoke(app, ["improve", "report"])
        assert result.exit_code == 0
        assert "2" in result.output

    def test_report_period_day(self, workspace: Path) -> None:
        _write_improvement(workspace, skill="s")
        result = runner.invoke(app, ["improve", "report", "--period", "day"])
        assert result.exit_code == 0
        assert "day" in result.output

    def test_report_period_month(self, workspace: Path) -> None:
        _write_improvement(workspace, skill="s")
        result = runner.invoke(app, ["improve", "report", "--period", "month"])
        assert result.exit_code == 0
        assert "month" in result.output
