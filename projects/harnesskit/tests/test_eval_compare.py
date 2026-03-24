"""Tests for Phase 5.4: A/B comparison of eval runs."""

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
from harness_kit.eval import compare_evals, run_eval

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
    "name": "ab-suite",
    "description": "A/B test suite",
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
# Unit tests for compare_evals
# ---------------------------------------------------------------------------


class TestCompareEvals:
    def _build_reports(
        self,
        workspace: Path,
        output_a: Any,
        output_b: Any,
        tokens_a: tuple[int, int] = (50, 50),
        tokens_b: tuple[int, int] = (50, 50),
        dur_a: float = 1.0,
        dur_b: float = 1.0,
    ) -> tuple[dict, dict]:
        em.save_suite(SUITE, workspace)
        report_a = run_eval("skill@v1", "ab-suite", _make_invoke(output_a, tokens_a, dur_a), base=workspace)
        report_b = run_eval("skill@v2", "ab-suite", _make_invoke(output_b, tokens_b, dur_b), base=workspace)
        return report_a, report_b

    def test_compare_structure(self, workspace: Path) -> None:
        output_pass = {"issues": [{"type": "empty_body"}], "summary": "ok"}
        ra, rb = self._build_reports(workspace, output_pass, output_pass)
        cmp = compare_evals(ra, rb)
        assert "target_a" in cmp
        assert "target_b" in cmp
        assert "suite" in cmp
        assert "metrics_a" in cmp
        assert "metrics_b" in cmp
        assert "case_diffs" in cmp
        assert "changed_cases" in cmp
        assert "verdict" in cmp

    def test_metrics_pass_rate(self, workspace: Path) -> None:
        output_pass = {"issues": [{"type": "empty_body"}], "summary": "ok"}
        output_fail = {"issues": [], "summary": "nope"}
        ra, rb = self._build_reports(workspace, output_pass, output_fail)
        cmp = compare_evals(ra, rb)
        # A has better pass rate (at least case-1 passes)
        assert cmp["metrics_a"]["pass_rate"] >= cmp["metrics_b"]["pass_rate"]

    def test_verdict_a_better(self, workspace: Path) -> None:
        """A passes all, B fails all — verdict should be 'a'."""
        output_pass = {"issues": [{"type": "empty_body"}], "summary": "ok正常"}
        output_fail = {}  # no matching fields
        ra, rb = self._build_reports(workspace, output_pass, output_fail)
        cmp = compare_evals(ra, rb)
        assert cmp["verdict"] == "a"

    def test_verdict_b_better(self, workspace: Path) -> None:
        """B passes more than A — verdict should be 'b'."""
        output_fail = {}
        output_pass = {"issues": [{"type": "empty_body"}], "summary": "ok正常"}
        ra, rb = self._build_reports(workspace, output_fail, output_pass)
        cmp = compare_evals(ra, rb)
        assert cmp["verdict"] == "b"

    def test_tie_breaks_on_tokens(self, workspace: Path) -> None:
        """Same pass rate: lower tokens wins."""
        output_both = {"issues": [{"type": "empty_body"}], "summary": "ok正常"}
        ra, rb = self._build_reports(
            workspace, output_both, output_both,
            tokens_a=(10, 10), tokens_b=(100, 100)
        )
        cmp = compare_evals(ra, rb)
        # A has fewer tokens → A wins
        assert cmp["verdict"] == "a"

    def test_case_diffs_all_same(self, workspace: Path) -> None:
        output_pass = {"issues": [{"type": "empty_body"}], "summary": "ok正常"}
        ra, rb = self._build_reports(workspace, output_pass, output_pass)
        cmp = compare_evals(ra, rb)
        assert cmp["changed_cases"] == []

    def test_case_diffs_detects_change(self, workspace: Path) -> None:
        output_pass = {"issues": [{"type": "empty_body"}], "summary": "ok正常"}
        output_fail = {}
        ra, rb = self._build_reports(workspace, output_pass, output_fail)
        cmp = compare_evals(ra, rb)
        # at least one case should have changed status
        assert len(cmp["changed_cases"]) >= 1
        for d in cmp["changed_cases"]:
            assert d["status_a"] != d["status_b"]
            assert d["changed"] is True

    def test_case_diffs_contains_all_ids(self, workspace: Path) -> None:
        output_pass = {"issues": [{"type": "empty_body"}], "summary": "ok正常"}
        ra, rb = self._build_reports(workspace, output_pass, output_pass)
        cmp = compare_evals(ra, rb)
        diff_ids = {d["id"] for d in cmp["case_diffs"]}
        assert "case-1" in diff_ids
        assert "case-2" in diff_ids

    def test_metrics_token_fields(self, workspace: Path) -> None:
        output_pass = {"issues": [{"type": "empty_body"}], "summary": "ok正常"}
        ra, rb = self._build_reports(workspace, output_pass, output_pass, tokens_a=(10, 20), tokens_b=(30, 40))
        cmp = compare_evals(ra, rb)
        assert cmp["metrics_a"]["total_tokens"] == (10 + 20) * 2  # 2 cases
        assert cmp["metrics_b"]["total_tokens"] == (30 + 40) * 2

    def test_target_labels_preserved(self, workspace: Path) -> None:
        output_pass = {"issues": [{"type": "empty_body"}], "summary": "ok正常"}
        ra, rb = self._build_reports(workspace, output_pass, output_pass)
        cmp = compare_evals(ra, rb)
        assert cmp["target_a"] == "skill@v1"
        assert cmp["target_b"] == "skill@v2"


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def compare_workspace(workspace: Path) -> Path:
    """Workspace with two skill versions and a test suite."""
    from harness_kit import skill as sm

    sm.save_skill(
        name="cmp-skill",
        description="Skill for compare testing",
        trigger="when needed",
        inputs=[{"name": "code", "type": "string", "required": True}],
        base=workspace,
    )
    # Second version
    sm.save_skill(
        name="cmp-skill",
        description="Skill v2 for compare testing",
        trigger="when needed",
        inputs=[{"name": "code", "type": "string", "required": True}],
        base=workspace,
    )

    suite_data = {
        "name": "cmp-suite",
        "description": "Compare eval suite",
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


class TestEvalCompareCLI:
    def _mock_llm_ok(self):
        mock_resp = MagicMock()
        mock_resp.content = '{"status": "ok"}'
        mock_resp.input_tokens = 10
        mock_resp.output_tokens = 20
        mock_resp.duration = 0.5
        return mock_resp

    def test_missing_a_option(self, compare_workspace: Path) -> None:
        result = runner.invoke(app, ["eval", "compare", "--b", "cmp-skill", "--suite", "cmp-suite"])
        assert result.exit_code != 0

    def test_missing_b_option(self, compare_workspace: Path) -> None:
        result = runner.invoke(app, ["eval", "compare", "--a", "cmp-skill", "--suite", "cmp-suite"])
        assert result.exit_code != 0

    def test_missing_suite_option(self, compare_workspace: Path) -> None:
        result = runner.invoke(app, ["eval", "compare", "--a", "cmp-skill", "--b", "cmp-skill"])
        assert result.exit_code != 0

    def test_nonexistent_suite(self, compare_workspace: Path) -> None:
        result = runner.invoke(app, ["eval", "compare", "--a", "cmp-skill", "--b", "cmp-skill",
                                     "--suite", "no-such-suite"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "✗" in result.output

    def test_nonexistent_skill_a(self, compare_workspace: Path) -> None:
        result = runner.invoke(app, ["eval", "compare", "--a", "no-skill", "--b", "cmp-skill",
                                     "--suite", "cmp-suite"])
        assert result.exit_code == 1

    def test_nonexistent_skill_b(self, compare_workspace: Path) -> None:
        result = runner.invoke(app, ["eval", "compare", "--a", "cmp-skill", "--b", "no-skill",
                                     "--suite", "cmp-suite"])
        assert result.exit_code == 1

    def test_successful_compare(self, compare_workspace: Path) -> None:
        mock_resp = self._mock_llm_ok()
        with (
            patch("harness_kit.cli.call_llm", return_value=mock_resp),
            patch("harness_kit.cli.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="test-key", model="gpt-test",
                                               base_url=None, temperature=0.7, max_tokens=None)
            result = runner.invoke(
                app,
                ["eval", "compare", "--a", "cmp-skill", "--b", "cmp-skill", "--suite", "cmp-suite"],
            )
        assert result.exit_code == 0
        # Should show comparison table
        assert "Metrics Comparison" in result.output or "A/B" in result.output
        # Should show recommendation
        assert "Recommendation" in result.output or "better" in result.output

    def test_compare_shows_targets(self, compare_workspace: Path) -> None:
        mock_resp = self._mock_llm_ok()
        with (
            patch("harness_kit.cli.call_llm", return_value=mock_resp),
            patch("harness_kit.cli.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="test-key", model="gpt-test",
                                               base_url=None, temperature=0.7, max_tokens=None)
            result = runner.invoke(
                app,
                ["eval", "compare", "--a", "cmp-skill", "--b", "cmp-skill", "--suite", "cmp-suite"],
            )
        assert "cmp-skill" in result.output

    def test_no_api_key_exits(self, compare_workspace: Path) -> None:
        with patch("harness_kit.cli.LLMConfig.from_harness_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(api_key=None, model="gpt-test",
                                               base_url=None, temperature=0.7, max_tokens=None)
            result = runner.invoke(
                app,
                ["eval", "compare", "--a", "cmp-skill", "--b", "cmp-skill", "--suite", "cmp-suite"],
            )
        assert result.exit_code == 1
        assert "API key" in result.output or "api_key" in result.output.lower()

    def test_ci_mode_exits_zero_when_all_pass(self, compare_workspace: Path) -> None:
        mock_resp = self._mock_llm_ok()
        with (
            patch("harness_kit.cli.call_llm", return_value=mock_resp),
            patch("harness_kit.cli.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="test-key", model="gpt-test",
                                               base_url=None, temperature=0.7, max_tokens=None)
            result = runner.invoke(
                app,
                ["eval", "compare", "--a", "cmp-skill", "--b", "cmp-skill",
                 "--suite", "cmp-suite", "--ci"],
            )
        assert result.exit_code == 0

    def test_ci_mode_exits_nonzero_when_failures(self, compare_workspace: Path) -> None:
        # Return output that will NOT match the assertion ($.status == "ok")
        mock_resp = MagicMock()
        mock_resp.content = '{"status": "error"}'
        mock_resp.input_tokens = 5
        mock_resp.output_tokens = 10
        mock_resp.duration = 0.1
        with (
            patch("harness_kit.cli.call_llm", return_value=mock_resp),
            patch("harness_kit.cli.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="test-key", model="gpt-test",
                                               base_url=None, temperature=0.7, max_tokens=None)
            result = runner.invoke(
                app,
                ["eval", "compare", "--a", "cmp-skill", "--b", "cmp-skill",
                 "--suite", "cmp-suite", "--ci"],
            )
        assert result.exit_code == 1
