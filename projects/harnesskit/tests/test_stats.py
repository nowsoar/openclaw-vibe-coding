"""Tests for Phase 6.3: 统计仪表盘 — stats dashboard."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness_kit import stats as stats_mod
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


def _write_record(base: Path, **kwargs) -> None:
    """Append a single call-log record to calls.jsonl."""
    log_file = base / ".harness" / "logs" / "calls.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "type": "llm_call",
        "skill": "test-skill",
        "model": "gpt-4o",
        "input_tokens": 400,
        "output_tokens": 100,
        "total_tokens": 500,
        "cost": 0.002,
        "duration": 1.5,
        "status": "success",
    }
    record.update(kwargs)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# Unit tests: skill_stats — empty state
# ---------------------------------------------------------------------------


class TestSkillStatsEmpty:
    def test_no_logs_returns_zero_calls(self, workspace: Path) -> None:
        data = stats_mod.skill_stats(target="missing-skill", base=workspace)
        assert data["total_calls"] == 0
        assert data["success_calls"] == 0
        assert data["error_calls"] == 0
        assert data["success_rate"] == 0.0
        assert data["total_cost"] == 0.0

    def test_empty_log_file_returns_zero(self, workspace: Path) -> None:
        log_file = workspace / ".harness" / "logs" / "calls.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text("", encoding="utf-8")
        data = stats_mod.skill_stats(target="any-skill", base=workspace)
        assert data["total_calls"] == 0


# ---------------------------------------------------------------------------
# Unit tests: skill_stats — call count and success rate
# ---------------------------------------------------------------------------


class TestCallCountAndSuccessRate:
    def test_counts_success_calls(self, workspace: Path) -> None:
        _write_record(workspace, skill="my-skill", status="success")
        _write_record(workspace, skill="my-skill", status="success")
        data = stats_mod.skill_stats(target="my-skill", base=workspace)
        assert data["total_calls"] == 2
        assert data["success_calls"] == 2
        assert data["error_calls"] == 0
        assert data["success_rate"] == 1.0

    def test_counts_error_calls(self, workspace: Path) -> None:
        _write_record(workspace, skill="my-skill", status="success")
        _write_record(workspace, skill="my-skill", status="error", error="timeout")
        data = stats_mod.skill_stats(target="my-skill", base=workspace)
        assert data["total_calls"] == 2
        assert data["success_calls"] == 1
        assert data["error_calls"] == 1
        assert data["success_rate"] == 0.5

    def test_filters_by_target(self, workspace: Path) -> None:
        _write_record(workspace, skill="skill-a", status="success")
        _write_record(workspace, skill="skill-b", status="success")
        _write_record(workspace, skill="skill-a", status="error", error="fail")

        data_a = stats_mod.skill_stats(target="skill-a", base=workspace)
        data_b = stats_mod.skill_stats(target="skill-b", base=workspace)

        assert data_a["total_calls"] == 2
        assert data_b["total_calls"] == 1

    def test_all_calls_when_target_none(self, workspace: Path) -> None:
        _write_record(workspace, skill="skill-a")
        _write_record(workspace, skill="skill-b")
        _write_record(workspace, skill="skill-c")
        data = stats_mod.skill_stats(target=None, base=workspace)
        assert data["total_calls"] == 3

    def test_hundred_percent_success(self, workspace: Path) -> None:
        for _ in range(5):
            _write_record(workspace, skill="perfect", status="success")
        data = stats_mod.skill_stats(target="perfect", base=workspace)
        assert data["success_rate"] == 1.0
        assert data["error_calls"] == 0

    def test_zero_percent_success(self, workspace: Path) -> None:
        for _ in range(3):
            _write_record(workspace, skill="broken", status="error", error="API error")
        data = stats_mod.skill_stats(target="broken", base=workspace)
        assert data["success_rate"] == 0.0
        assert data["success_calls"] == 0


# ---------------------------------------------------------------------------
# Unit tests: skill_stats — duration stats
# ---------------------------------------------------------------------------


class TestDurationStats:
    def test_avg_duration(self, workspace: Path) -> None:
        _write_record(workspace, skill="s", duration=1.0)
        _write_record(workspace, skill="s", duration=3.0)
        data = stats_mod.skill_stats(target="s", base=workspace)
        assert data["avg_duration"] == pytest.approx(2.0, abs=0.01)

    def test_min_max_duration(self, workspace: Path) -> None:
        _write_record(workspace, skill="s", duration=0.5)
        _write_record(workspace, skill="s", duration=5.0)
        _write_record(workspace, skill="s", duration=2.5)
        data = stats_mod.skill_stats(target="s", base=workspace)
        assert data["min_duration"] == pytest.approx(0.5, abs=0.01)
        assert data["max_duration"] == pytest.approx(5.0, abs=0.01)

    def test_duration_buckets_populated(self, workspace: Path) -> None:
        _write_record(workspace, skill="s", duration=0.5)   # 0–1s
        _write_record(workspace, skill="s", duration=2.0)   # 1–3s
        _write_record(workspace, skill="s", duration=7.0)   # 5–10s
        data = stats_mod.skill_stats(target="s", base=workspace)
        assert data["duration_buckets"].get("0–1s", 0) == 1
        assert data["duration_buckets"].get("1–3s", 0) == 1
        assert data["duration_buckets"].get("5–10s", 0) == 1


# ---------------------------------------------------------------------------
# Unit tests: skill_stats — token distribution
# ---------------------------------------------------------------------------


class TestTokenDistribution:
    def test_avg_tokens(self, workspace: Path) -> None:
        _write_record(workspace, skill="s", input_tokens=200, output_tokens=100, total_tokens=300)
        _write_record(workspace, skill="s", input_tokens=400, output_tokens=200, total_tokens=600)
        data = stats_mod.skill_stats(target="s", base=workspace)
        assert data["avg_input_tokens"] == pytest.approx(300, abs=0.5)
        assert data["avg_output_tokens"] == pytest.approx(150, abs=0.5)
        assert data["avg_total_tokens"] == pytest.approx(450, abs=0.5)

    def test_total_tokens(self, workspace: Path) -> None:
        _write_record(workspace, skill="s", total_tokens=500)
        _write_record(workspace, skill="s", total_tokens=1500)
        data = stats_mod.skill_stats(target="s", base=workspace)
        assert data["total_tokens"] == 2000

    def test_token_buckets_populated(self, workspace: Path) -> None:
        _write_record(workspace, skill="s", total_tokens=50)    # 0–100
        _write_record(workspace, skill="s", total_tokens=300)   # 251–500
        _write_record(workspace, skill="s", total_tokens=3000)  # 2K–5K
        data = stats_mod.skill_stats(target="s", base=workspace)
        assert data["token_buckets"].get("0–100", 0) == 1
        assert data["token_buckets"].get("251–500", 0) == 1
        assert data["token_buckets"].get("2K–5K", 0) == 1


# ---------------------------------------------------------------------------
# Unit tests: skill_stats — error type distribution
# ---------------------------------------------------------------------------


class TestErrorTypeDistribution:
    def test_error_types_counted(self, workspace: Path) -> None:
        _write_record(workspace, skill="s", status="error", error="timeout")
        _write_record(workspace, skill="s", status="error", error="timeout")
        _write_record(workspace, skill="s", status="error", error="rate limit exceeded")
        data = stats_mod.skill_stats(target="s", base=workspace)
        assert data["error_types"].get("timeout", 0) == 2
        assert data["error_types"].get("rate limit exceeded", 0) == 1

    def test_no_errors_means_empty_error_types(self, workspace: Path) -> None:
        _write_record(workspace, skill="s", status="success")
        data = stats_mod.skill_stats(target="s", base=workspace)
        assert data["error_types"] == {}


# ---------------------------------------------------------------------------
# Unit tests: skill_stats — model usage and cost
# ---------------------------------------------------------------------------


class TestModelAndCost:
    def test_models_used(self, workspace: Path) -> None:
        _write_record(workspace, skill="s", model="gpt-4o")
        _write_record(workspace, skill="s", model="gpt-4o")
        _write_record(workspace, skill="s", model="gpt-4o-mini")
        data = stats_mod.skill_stats(target="s", base=workspace)
        assert data["models_used"].get("gpt-4o", 0) == 2
        assert data["models_used"].get("gpt-4o-mini", 0) == 1

    def test_total_cost_accumulated(self, workspace: Path) -> None:
        _write_record(workspace, skill="s", cost=0.01)
        _write_record(workspace, skill="s", cost=0.02)
        data = stats_mod.skill_stats(target="s", base=workspace)
        assert data["total_cost"] == pytest.approx(0.03, abs=1e-7)

    def test_avg_cost(self, workspace: Path) -> None:
        _write_record(workspace, skill="s", cost=0.01)
        _write_record(workspace, skill="s", cost=0.03)
        data = stats_mod.skill_stats(target="s", base=workspace)
        assert data["avg_cost"] == pytest.approx(0.02, abs=1e-7)

    def test_cost_none_records_skipped(self, workspace: Path) -> None:
        _write_record(workspace, skill="s", cost=None)
        _write_record(workspace, skill="s", cost=0.05)
        data = stats_mod.skill_stats(target="s", base=workspace)
        # total_cost should only sum non-None records
        assert data["total_cost"] == pytest.approx(0.05, abs=1e-7)


# ---------------------------------------------------------------------------
# Unit tests: bar_chart_rows
# ---------------------------------------------------------------------------


class TestBarChartRows:
    def test_returns_rows_for_each_bucket(self) -> None:
        buckets = {"A": 10, "B": 5, "C": 1}
        rows = stats_mod.bar_chart_rows(buckets, bar_width=20)
        assert len(rows) == 3
        labels = [r[0] for r in rows]
        assert "A" in labels
        assert "B" in labels
        assert "C" in labels

    def test_max_bar_is_full_width(self) -> None:
        buckets = {"big": 100, "small": 1}
        rows = stats_mod.bar_chart_rows(buckets, bar_width=20)
        big_row = next(r for r in rows if r[0] == "big")
        # bar string contains 20 filled chars (█)
        assert big_row[2].count("█") == 20

    def test_empty_buckets_returns_empty(self) -> None:
        rows = stats_mod.bar_chart_rows({}, bar_width=20)
        assert rows == []

    def test_counts_correct(self) -> None:
        buckets = {"x": 42}
        rows = stats_mod.bar_chart_rows(buckets)
        assert rows[0][1] == 42


# ---------------------------------------------------------------------------
# CLI integration tests: stats show
# ---------------------------------------------------------------------------


class TestStatsShowCli:
    def test_show_no_logs_prints_not_found(self, workspace: Path) -> None:
        result = runner.invoke(app, ["stats", "show", "nonexistent-skill"])
        assert result.exit_code == 0
        assert "No call logs found" in result.output

    def test_show_with_data_displays_overview(self, workspace: Path) -> None:
        _write_record(workspace, skill="demo-skill", status="success", duration=1.2)
        _write_record(workspace, skill="demo-skill", status="success", duration=2.4)
        result = runner.invoke(app, ["stats", "show", "demo-skill"])
        assert result.exit_code == 0
        assert "demo-skill" in result.output
        assert "Total calls" in result.output
        assert "Success rate" in result.output

    def test_show_displays_error_distribution(self, workspace: Path) -> None:
        _write_record(workspace, skill="s", status="error", error="timeout error")
        result = runner.invoke(app, ["stats", "show", "s"])
        assert result.exit_code == 0
        assert "timeout error" in result.output

    def test_show_displays_token_chart(self, workspace: Path) -> None:
        _write_record(workspace, skill="s", total_tokens=200, status="success")
        result = runner.invoke(app, ["stats", "show", "s"])
        assert result.exit_code == 0
        assert "Token Consumption" in result.output

    def test_show_success_rate_correct(self, workspace: Path) -> None:
        for _ in range(3):
            _write_record(workspace, skill="s", status="success")
        _write_record(workspace, skill="s", status="error", error="fail")
        result = runner.invoke(app, ["stats", "show", "s"])
        assert result.exit_code == 0
        assert "75.0%" in result.output

    def test_show_since_option_works(self, workspace: Path) -> None:
        _write_record(workspace, skill="s", status="success")
        result = runner.invoke(app, ["stats", "show", "s", "--since", "7d"])
        assert result.exit_code == 0
        assert "last 7d" in result.output

    def test_show_all_success_message(self, workspace: Path) -> None:
        _write_record(workspace, skill="s", status="success")
        result = runner.invoke(app, ["stats", "show", "s"])
        assert result.exit_code == 0
        assert "all calls succeeded" in result.output

    def test_show_not_initialized_exits_with_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["stats", "show", "my-skill"])
        assert result.exit_code != 0
