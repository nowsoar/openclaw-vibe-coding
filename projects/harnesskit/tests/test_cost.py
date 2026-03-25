"""Tests for Phase 6.2: 成本追踪 — cost tracking system."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness_kit import cost_tracker as ct
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
    """Write a single log record directly to calls.jsonl."""
    log_file = base / ".harness" / "logs" / "calls.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "type": "llm_call",
        "skill": "test-skill",
        "model": "gpt-4o",
        "input_tokens": 1000,
        "output_tokens": 500,
        "total_tokens": 1500,
        "cost": None,
        "duration": 1.5,
        "status": "success",
    }
    record.update(kwargs)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# Unit tests: estimate_cost
# ---------------------------------------------------------------------------


class TestEstimateCost:
    def test_known_model_gpt4o(self, workspace: Path) -> None:
        # gpt-4o: input $0.0025/1K, output $0.010/1K
        # 1000 input + 500 output = 1 * 0.0025 + 0.5 * 0.010 = 0.0025 + 0.005 = 0.0075
        cost = ct.estimate_cost("gpt-4o", 1000, 500, base=workspace)
        assert cost is not None
        assert abs(cost - 0.0075) < 1e-8

    def test_known_model_gpt4o_mini(self, workspace: Path) -> None:
        # input $0.00015/1K, output $0.0006/1K
        # 2000 input + 1000 output = 2*0.00015 + 1*0.0006 = 0.0003 + 0.0006 = 0.0009
        cost = ct.estimate_cost("gpt-4o-mini", 2000, 1000, base=workspace)
        assert cost is not None
        assert abs(cost - 0.0009) < 1e-8

    def test_unknown_model_returns_none(self, workspace: Path) -> None:
        cost = ct.estimate_cost("unknown-model-xyz", 100, 50, base=workspace)
        assert cost is None

    def test_zero_tokens(self, workspace: Path) -> None:
        cost = ct.estimate_cost("gpt-4o", 0, 0, base=workspace)
        assert cost == 0.0

    def test_claude_model(self, workspace: Path) -> None:
        # claude-3-5-sonnet: input $0.003/1K, output $0.015/1K
        cost = ct.estimate_cost("claude-3-5-sonnet", 1000, 1000, base=workspace)
        assert cost is not None
        assert abs(cost - (0.003 + 0.015)) < 1e-8

    def test_case_insensitive(self, workspace: Path) -> None:
        cost_lower = ct.estimate_cost("gpt-4o", 1000, 500, base=workspace)
        cost_upper = ct.estimate_cost("GPT-4O", 1000, 500, base=workspace)
        assert cost_lower == cost_upper


# ---------------------------------------------------------------------------
# Unit tests: get_model_prices / set_model_price
# ---------------------------------------------------------------------------


class TestModelPrices:
    def test_default_prices_populated(self, workspace: Path) -> None:
        prices = ct.get_model_prices(base=workspace)
        assert "gpt-4o" in prices
        assert "gpt-4o-mini" in prices
        assert "claude-3-5-sonnet" in prices
        assert "deepseek-v3" in prices

    def test_set_and_get_custom_price(self, workspace: Path) -> None:
        ct.set_model_price("my-custom-model", 0.001, 0.002, base=workspace)
        prices = ct.get_model_prices(base=workspace)
        assert "my-custom-model" in prices
        assert prices["my-custom-model"]["input"] == 0.001
        assert prices["my-custom-model"]["output"] == 0.002

    def test_custom_price_overrides_default(self, workspace: Path) -> None:
        ct.set_model_price("gpt-4o", 0.999, 0.999, base=workspace)
        cost = ct.estimate_cost("gpt-4o", 1000, 0, base=workspace)
        assert cost is not None
        assert abs(cost - 0.999) < 1e-6

    def test_set_price_persists_to_config(self, workspace: Path) -> None:
        ct.set_model_price("test-model", 0.01, 0.02, base=workspace)
        from harness_kit.config import read_config
        cfg = read_config(base=workspace)
        assert "model_pricing" in cfg
        assert "test-model" in cfg["model_pricing"]


# ---------------------------------------------------------------------------
# Unit tests: cost_report
# ---------------------------------------------------------------------------


class TestCostReport:
    def test_empty_logs(self, workspace: Path) -> None:
        report = ct.cost_report(since="30d", base=workspace)
        assert report["total_cost"] == 0.0
        assert report["total_calls"] == 0
        assert report["total_tokens"] == 0
        assert report["by_skill"] == {}
        assert report["by_model"] == {}

    def test_basic_report(self, workspace: Path) -> None:
        _write_record(workspace, skill="skill-a", model="gpt-4o", cost=0.01,
                      input_tokens=1000, output_tokens=500, total_tokens=1500)
        _write_record(workspace, skill="skill-a", model="gpt-4o", cost=0.02,
                      input_tokens=2000, output_tokens=1000, total_tokens=3000)
        _write_record(workspace, skill="skill-b", model="gpt-4o-mini", cost=0.005,
                      input_tokens=500, output_tokens=200, total_tokens=700)
        report = ct.cost_report(since="30d", base=workspace)
        assert report["total_calls"] == 3
        assert abs(report["total_cost"] - 0.035) < 1e-8
        assert "skill-a" in report["by_skill"]
        assert "skill-b" in report["by_skill"]
        assert abs(report["by_skill"]["skill-a"]["cost"] - 0.03) < 1e-8
        assert report["by_skill"]["skill-a"]["calls"] == 2

    def test_by_model_grouping(self, workspace: Path) -> None:
        _write_record(workspace, model="gpt-4o", cost=0.01)
        _write_record(workspace, model="gpt-4o-mini", cost=0.001)
        report = ct.cost_report(since="30d", base=workspace)
        assert "gpt-4o" in report["by_model"]
        assert "gpt-4o-mini" in report["by_model"]

    def test_most_expensive_call(self, workspace: Path) -> None:
        _write_record(workspace, cost=0.001, skill="cheap")
        _write_record(workspace, cost=0.999, skill="expensive", model="gpt-4")
        report = ct.cost_report(since="30d", base=workspace)
        top = report["most_expensive_call"]
        assert top is not None
        assert top["skill"] == "expensive"
        assert abs(top["cost"] - 0.999) < 1e-8

    def test_daily_breakdown(self, workspace: Path) -> None:
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        _write_record(workspace, cost=0.05)
        report = ct.cost_report(since="1d", base=workspace)
        assert today in report["daily_breakdown"]
        assert abs(report["daily_breakdown"][today] - 0.05) < 1e-8

    def test_records_without_cost_estimated(self, workspace: Path) -> None:
        # Write record with cost=None — should be estimated from tokens+model
        _write_record(workspace, model="gpt-4o", cost=None,
                      input_tokens=1000, output_tokens=500, total_tokens=1500)
        report = ct.cost_report(since="30d", base=workspace)
        # gpt-4o: 1*0.0025 + 0.5*0.010 = 0.0075
        assert report["total_cost"] > 0.0


# ---------------------------------------------------------------------------
# Unit tests: check_cost_alert
# ---------------------------------------------------------------------------


class TestCostAlert:
    def test_alert_triggered_when_over_threshold(self, workspace: Path) -> None:
        triggered, cost = ct.check_cost_alert(
            "gpt-4o", 10000, 5000, threshold=0.01, base=workspace
        )
        assert cost is not None
        # 10*0.0025 + 5*0.010 = 0.025 + 0.050 = 0.075 > 0.01
        assert triggered is True

    def test_no_alert_when_under_threshold(self, workspace: Path) -> None:
        triggered, cost = ct.check_cost_alert(
            "gpt-4o", 100, 50, threshold=1.0, base=workspace
        )
        assert triggered is False

    def test_no_alert_for_unknown_model(self, workspace: Path) -> None:
        triggered, cost = ct.check_cost_alert(
            "unknown-model", 1000, 500, threshold=0.001, base=workspace
        )
        assert triggered is False
        assert cost is None

    def test_threshold_from_config(self, workspace: Path) -> None:
        # Set threshold in config
        from harness_kit.config import read_config, write_config
        cfg = read_config(base=workspace)
        cfg["cost_alert"] = {"per_call": 0.001}
        write_config(cfg, base=workspace)

        # gpt-4o with 10K/5K tokens = $0.075, exceeds threshold=0.001
        triggered, cost = ct.check_cost_alert(
            "gpt-4o", 10000, 5000, base=workspace
        )
        assert triggered is True


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestCostReportCLI:
    def test_cost_report_no_data(self, workspace: Path) -> None:
        result = runner.invoke(app, ["cost", "report"])
        assert result.exit_code == 0
        assert "No data" in result.output

    def test_cost_report_with_data(self, workspace: Path) -> None:
        _write_record(workspace, skill="my-skill", model="gpt-4o", cost=0.05,
                      input_tokens=5000, output_tokens=2000, total_tokens=7000)
        result = runner.invoke(app, ["cost", "report", "--since", "30d"])
        assert result.exit_code == 0
        assert "Cost Report" in result.output
        assert "my-skill" in result.output
        assert "$0.0500" in result.output

    def test_cost_report_group_by_model(self, workspace: Path) -> None:
        _write_record(workspace, model="gpt-4o", cost=0.01)
        _write_record(workspace, model="gpt-4o-mini", cost=0.001)
        result = runner.invoke(app, ["cost", "report", "--group-by", "model"])
        assert result.exit_code == 0
        assert "gpt-4o" in result.output

    def test_cost_report_group_by_day(self, workspace: Path) -> None:
        _write_record(workspace, cost=0.05)
        result = runner.invoke(app, ["cost", "report", "--group-by", "day"])
        assert result.exit_code == 0
        assert "Cost by Day" in result.output

    def test_cost_report_not_initialized(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["cost", "report"])
        assert result.exit_code != 0
        assert "Not initialized" in result.output


class TestCostBreakdownCLI:
    def test_breakdown_no_data(self, workspace: Path) -> None:
        result = runner.invoke(app, ["cost", "breakdown"])
        assert result.exit_code == 0
        assert "No call logs" in result.output

    def test_breakdown_with_data(self, workspace: Path) -> None:
        for i in range(3):
            _write_record(workspace, skill=f"skill-{i}", cost=0.01 * (i + 1))
        result = runner.invoke(app, ["cost", "breakdown"])
        assert result.exit_code == 0
        assert "Most Expensive" in result.output

    def test_breakdown_sorted_by_cost(self, workspace: Path) -> None:
        _write_record(workspace, skill="cheap", cost=0.001)
        _write_record(workspace, skill="expensive", cost=0.999)
        result = runner.invoke(app, ["cost", "breakdown", "--limit", "2"])
        assert result.exit_code == 0
        # expensive should appear before cheap in output
        assert result.output.index("expensive") < result.output.index("cheap")

    def test_breakdown_filter_by_skill(self, workspace: Path) -> None:
        _write_record(workspace, skill="keep-this", cost=0.01)
        _write_record(workspace, skill="filter-out", cost=0.01)
        result = runner.invoke(app, ["cost", "breakdown", "--skill", "keep-this"])
        assert result.exit_code == 0
        assert "keep-this" in result.output
        assert "filter-out" not in result.output


class TestCostSetPriceCLI:
    def test_set_price(self, workspace: Path) -> None:
        result = runner.invoke(
            app, ["cost", "set-price", "my-model", "--input", "0.001", "--output", "0.002"]
        )
        assert result.exit_code == 0
        assert "Price set" in result.output
        assert "my-model" in result.output
        # Verify it was saved
        prices = ct.get_model_prices(base=workspace)
        assert "my-model" in prices
        assert prices["my-model"]["input"] == 0.001
        assert prices["my-model"]["output"] == 0.002

    def test_list_prices(self, workspace: Path) -> None:
        result = runner.invoke(app, ["cost", "list-prices"])
        assert result.exit_code == 0
        assert "gpt-4o" in result.output
        assert "Model Pricing" in result.output


class TestCostIntegration:
    """Integration: cost flows through log_call correctly."""

    def test_estimate_cost_gpt4o_accuracy(self, workspace: Path) -> None:
        # Verify formula: cost = (in/1000)*rate_in + (out/1000)*rate_out
        cost = ct.estimate_cost("gpt-4o", 1000, 0, base=workspace)
        assert cost is not None
        assert abs(cost - 0.0025) < 1e-9

        cost2 = ct.estimate_cost("gpt-4o", 0, 1000, base=workspace)
        assert cost2 is not None
        assert abs(cost2 - 0.010) < 1e-9

    def test_cost_report_uses_stored_cost(self, workspace: Path) -> None:
        """Report uses pre-stored cost values, not re-estimated."""
        _write_record(workspace, cost=1.23456)
        report = ct.cost_report(since="30d", base=workspace)
        assert abs(report["total_cost"] - 1.23456) < 1e-5

    def test_cost_report_since_filter(self, workspace: Path) -> None:
        """Records outside the time window are excluded."""
        # Write a record with a very old timestamp
        log_file = workspace / ".harness" / "logs" / "calls.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        old_record = {
            "timestamp": "2000-01-01T00:00:00+00:00",
            "type": "llm_call",
            "skill": "old-skill",
            "model": "gpt-4o",
            "input_tokens": 1000,
            "output_tokens": 500,
            "total_tokens": 1500,
            "cost": 999.0,
            "duration": 1.0,
            "status": "success",
        }
        with log_file.open("a") as f:
            f.write(json.dumps(old_record) + "\n")

        report = ct.cost_report(since="1d", base=workspace)
        assert report["total_cost"] < 999.0  # old record excluded
