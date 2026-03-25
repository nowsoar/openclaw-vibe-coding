"""Tests for Phase 5.5: Multi-model Benchmark."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from harness_kit import eval as em
from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit.eval import benchmark_evals, run_eval

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


SUITE: dict[str, Any] = {
    "name": "bench-suite",
    "description": "Benchmark test suite",
    "cases": [
        {
            "id": "case-1",
            "name": "Check issues field",
            "inputs": {"code": "def foo(): pass"},
            "assertions": [
                {"type": "contains", "path": "$.issues[*].type", "value": "empty_body"},
            ],
        },
        {
            "id": "case-2",
            "name": "Check summary",
            "inputs": {"code": "x = 1"},
            "assertions": [
                {"type": "regex", "path": "$.summary", "pattern": "ok|正常"},
            ],
        },
    ],
}


def _make_invoke(output: Any, tokens: tuple[int, int] = (50, 100), duration: float = 1.0):
    def _invoke(inputs: dict) -> tuple[str, int, int, float]:
        return json.dumps(output), tokens[0], tokens[1], duration
    return _invoke


# ---------------------------------------------------------------------------
# Unit tests for benchmark_evals
# ---------------------------------------------------------------------------


class TestBenchmarkEvals:
    def _make_report(
        self,
        workspace: Path,
        model: str,
        output: Any,
        tokens: tuple[int, int] = (50, 50),
        duration: float = 1.0,
    ) -> dict:
        em.save_suite(SUITE, workspace)
        return run_eval(
            target=f"bench-skill@v0.1.0 [{model}]",
            suite_name="bench-suite",
            invoke_fn=_make_invoke(output, tokens, duration),
            base=workspace,
            extra_fields={"model": model, "skill": "bench-skill@v0.1.0"},
        )

    def test_benchmark_structure(self, workspace: Path) -> None:
        output = {"issues": [{"type": "empty_body"}], "summary": "ok正常"}
        ra = self._make_report(workspace, "model-a", output)
        rb = self._make_report(workspace, "model-b", output)
        result = benchmark_evals([ra, rb])
        assert "entries" in result
        assert "best_model" in result
        assert "suite" in result
        assert len(result["entries"]) == 2

    def test_entries_have_model_and_metrics(self, workspace: Path) -> None:
        output = {"issues": [{"type": "empty_body"}], "summary": "ok正常"}
        ra = self._make_report(workspace, "gpt-4o", output)
        rb = self._make_report(workspace, "claude-3-5", output)
        result = benchmark_evals([ra, rb])
        models = [e["model"] for e in result["entries"]]
        assert "gpt-4o" in models
        assert "claude-3-5" in models
        for entry in result["entries"]:
            assert "metrics" in entry
            m = entry["metrics"]
            assert "pass_rate" in m
            assert "avg_tokens" in m
            assert "avg_duration" in m

    def test_best_model_highest_pass_rate(self, workspace: Path) -> None:
        """Model with higher pass rate wins."""
        em.save_suite(SUITE, workspace)
        output_pass = {"issues": [{"type": "empty_body"}], "summary": "ok正常"}
        output_fail = {"issues": [], "summary": "nope"}

        ra = run_eval(
            "bench-skill@v0.1.0 [model-a]", "bench-suite",
            _make_invoke(output_pass), base=workspace,
            extra_fields={"model": "model-a"},
        )
        rb = run_eval(
            "bench-skill@v0.1.0 [model-b]", "bench-suite",
            _make_invoke(output_fail), base=workspace,
            extra_fields={"model": "model-b"},
        )
        result = benchmark_evals([ra, rb])
        assert result["best_model"] == "model-a"

    def test_best_model_tiebreak_on_tokens(self, workspace: Path) -> None:
        """When pass rates are equal, fewer tokens wins."""
        em.save_suite(SUITE, workspace)
        output_pass = {"issues": [{"type": "empty_body"}], "summary": "ok正常"}

        ra = run_eval(
            "bench-skill@v0.1.0 [cheap-model]", "bench-suite",
            _make_invoke(output_pass, tokens=(10, 20)), base=workspace,
            extra_fields={"model": "cheap-model"},
        )
        rb = run_eval(
            "bench-skill@v0.1.0 [expensive-model]", "bench-suite",
            _make_invoke(output_pass, tokens=(100, 200)), base=workspace,
            extra_fields={"model": "expensive-model"},
        )
        result = benchmark_evals([ra, rb])
        assert result["best_model"] == "cheap-model"

    def test_best_model_tiebreak_on_duration(self, workspace: Path) -> None:
        """When pass rate and tokens are equal, faster wins."""
        em.save_suite(SUITE, workspace)
        output_pass = {"issues": [{"type": "empty_body"}], "summary": "ok正常"}
        tokens = (50, 50)

        ra = run_eval(
            "bench-skill@v0.1.0 [fast-model]", "bench-suite",
            _make_invoke(output_pass, tokens, duration=0.5), base=workspace,
            extra_fields={"model": "fast-model"},
        )
        rb = run_eval(
            "bench-skill@v0.1.0 [slow-model]", "bench-suite",
            _make_invoke(output_pass, tokens, duration=5.0), base=workspace,
            extra_fields={"model": "slow-model"},
        )
        result = benchmark_evals([ra, rb])
        assert result["best_model"] == "fast-model"

    def test_three_models(self, workspace: Path) -> None:
        """Three models; middle one wins on pass rate."""
        em.save_suite(SUITE, workspace)
        output_all_pass = {"issues": [{"type": "empty_body"}], "summary": "ok正常"}
        output_partial = {"issues": [{"type": "empty_body"}], "summary": "nope"}
        output_all_fail = {"issues": [], "summary": "nope"}

        r1 = run_eval(
            "s [m1]", "bench-suite", _make_invoke(output_all_pass), base=workspace,
            extra_fields={"model": "m1"},
        )
        r2 = run_eval(
            "s [m2]", "bench-suite", _make_invoke(output_partial), base=workspace,
            extra_fields={"model": "m2"},
        )
        r3 = run_eval(
            "s [m3]", "bench-suite", _make_invoke(output_all_fail), base=workspace,
            extra_fields={"model": "m3"},
        )
        result = benchmark_evals([r1, r2, r3])
        assert result["best_model"] == "m1"
        assert len(result["entries"]) == 3

    def test_extra_fields_stored_in_report(self, workspace: Path) -> None:
        """run_eval should store extra_fields in the report."""
        em.save_suite(SUITE, workspace)
        output = {"issues": [{"type": "empty_body"}], "summary": "ok正常"}
        report = run_eval(
            "target", "bench-suite", _make_invoke(output), base=workspace,
            extra_fields={"model": "gpt-4o", "skill": "my-skill@v1"},
        )
        assert report.get("model") == "gpt-4o"
        assert report.get("skill") == "my-skill@v1"

    def test_suite_field_in_benchmark(self, workspace: Path) -> None:
        em.save_suite(SUITE, workspace)
        output = {"issues": [{"type": "empty_body"}], "summary": "ok正常"}
        ra = run_eval("t [m1]", "bench-suite", _make_invoke(output), base=workspace,
                      extra_fields={"model": "m1"})
        result = benchmark_evals([ra])
        assert result["suite"] == "bench-suite"


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def bench_workspace(workspace: Path) -> Path:
    """Workspace with a skill and a test suite for benchmark testing."""
    from harness_kit import skill as sm

    sm.save_skill(
        name="bench-skill",
        description="Skill for benchmark testing",
        trigger="when needed",
        inputs=[{"name": "code", "type": "string", "required": True}],
        base=workspace,
    )

    suite_data = {
        "name": "bench-cli-suite",
        "description": "CLI benchmark suite",
        "cases": [
            {
                "id": "c1",
                "name": "Check output",
                "inputs": {"code": "print('hi')"},
                "assertions": [
                    {"type": "contains", "path": "$.status", "value": "ok"},
                ],
            }
        ],
    }
    em.save_suite(suite_data, workspace)
    return workspace


class TestEvalBenchmarkCLI:
    def _mock_llm_ok(self) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.content = '{"status": "ok"}'
        mock_resp.input_tokens = 10
        mock_resp.output_tokens = 20
        mock_resp.duration = 0.5
        return mock_resp

    def test_missing_suite_option(self, bench_workspace: Path) -> None:
        result = runner.invoke(
            app, ["eval", "benchmark", "bench-skill", "--models", "gpt-4o"]
        )
        assert result.exit_code != 0

    def test_missing_models_option(self, bench_workspace: Path) -> None:
        result = runner.invoke(
            app, ["eval", "benchmark", "bench-skill", "--suite", "bench-cli-suite"]
        )
        assert result.exit_code != 0

    def test_nonexistent_suite(self, bench_workspace: Path) -> None:
        result = runner.invoke(
            app,
            ["eval", "benchmark", "bench-skill", "--suite", "no-such-suite",
             "--models", "gpt-4o"],
        )
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "✗" in result.output

    def test_nonexistent_skill(self, bench_workspace: Path) -> None:
        result = runner.invoke(
            app,
            ["eval", "benchmark", "no-skill", "--suite", "bench-cli-suite",
             "--models", "gpt-4o"],
        )
        assert result.exit_code == 1

    def test_no_api_key(self, bench_workspace: Path) -> None:
        with patch("harness_kit.cli.LLMConfig.from_harness_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(api_key=None, model="gpt-4o",
                                               base_url=None, temperature=0.7, max_tokens=None)
            result = runner.invoke(
                app,
                ["eval", "benchmark", "bench-skill", "--suite", "bench-cli-suite",
                 "--models", "gpt-4o"],
            )
        assert result.exit_code == 1
        assert "api key" in result.output.lower() or "✗" in result.output

    def test_successful_benchmark_single_model(self, bench_workspace: Path) -> None:
        mock_resp = self._mock_llm_ok()
        with (
            patch("harness_kit.cli.call_llm", return_value=mock_resp),
            patch("harness_kit.cli.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="test-key", model="gpt-4o",
                                               base_url=None, temperature=0.7, max_tokens=None)
            result = runner.invoke(
                app,
                ["eval", "benchmark", "bench-skill", "--suite", "bench-cli-suite",
                 "--models", "gpt-4o"],
            )
        assert result.exit_code == 0
        assert "gpt-4o" in result.output
        assert "Best Model" in result.output or "best" in result.output.lower()

    def test_successful_benchmark_multi_model(self, bench_workspace: Path) -> None:
        mock_resp = self._mock_llm_ok()
        with (
            patch("harness_kit.cli.call_llm", return_value=mock_resp),
            patch("harness_kit.cli.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="test-key", model="gpt-4o",
                                               base_url=None, temperature=0.7, max_tokens=None)
            result = runner.invoke(
                app,
                ["eval", "benchmark", "bench-skill", "--suite", "bench-cli-suite",
                 "--models", "gpt-4o,claude-3-5,deepseek-v3"],
            )
        assert result.exit_code == 0
        assert "gpt-4o" in result.output
        assert "claude-3-5" in result.output
        assert "deepseek-v3" in result.output

    def test_benchmark_shows_pass_rate(self, bench_workspace: Path) -> None:
        mock_resp = self._mock_llm_ok()
        with (
            patch("harness_kit.cli.call_llm", return_value=mock_resp),
            patch("harness_kit.cli.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="test-key", model="gpt-4o",
                                               base_url=None, temperature=0.7, max_tokens=None)
            result = runner.invoke(
                app,
                ["eval", "benchmark", "bench-skill", "--suite", "bench-cli-suite",
                 "--models", "gpt-4o,claude-3-5"],
            )
        assert result.exit_code == 0
        # Should display pass rate percentages
        assert "%" in result.output
        # Should display a comparison table
        assert "Benchmark" in result.output or "Pass Rate" in result.output

    def test_ci_mode_passes_when_all_pass(self, bench_workspace: Path) -> None:
        mock_resp = self._mock_llm_ok()
        with (
            patch("harness_kit.cli.call_llm", return_value=mock_resp),
            patch("harness_kit.cli.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="test-key", model="gpt-4o",
                                               base_url=None, temperature=0.7, max_tokens=None)
            result = runner.invoke(
                app,
                ["eval", "benchmark", "bench-skill", "--suite", "bench-cli-suite",
                 "--models", "gpt-4o", "--ci"],
            )
        assert result.exit_code == 0

    def test_ci_mode_fails_when_failures_exist(self, bench_workspace: Path) -> None:
        mock_resp = MagicMock()
        mock_resp.content = '{"status": "bad"}'  # won't match "ok"
        mock_resp.input_tokens = 10
        mock_resp.output_tokens = 20
        mock_resp.duration = 0.5
        with (
            patch("harness_kit.cli.call_llm", return_value=mock_resp),
            patch("harness_kit.cli.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="test-key", model="gpt-4o",
                                               base_url=None, temperature=0.7, max_tokens=None)
            result = runner.invoke(
                app,
                ["eval", "benchmark", "bench-skill", "--suite", "bench-cli-suite",
                 "--models", "gpt-4o", "--ci"],
            )
        assert result.exit_code == 1

    def test_benchmark_skill_label_in_output(self, bench_workspace: Path) -> None:
        mock_resp = self._mock_llm_ok()
        with (
            patch("harness_kit.cli.call_llm", return_value=mock_resp),
            patch("harness_kit.cli.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="test-key", model="gpt-4o",
                                               base_url=None, temperature=0.7, max_tokens=None)
            result = runner.invoke(
                app,
                ["eval", "benchmark", "bench-skill", "--suite", "bench-cli-suite",
                 "--models", "gpt-4o"],
            )
        assert "bench-skill" in result.output
