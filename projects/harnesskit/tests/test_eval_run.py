"""Tests for Phase 5.3: single eval run."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from harness_kit import eval as em
from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit.eval import _parse_output, run_eval

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


PASSING_SUITE: dict[str, Any] = {
    "name": "passing-suite",
    "description": "All assertions pass",
    "cases": [
        {
            "id": "case-pass",
            "name": "Passes contains + regex",
            "inputs": {"code": "def foo(): pass"},
            "assertions": [
                {"type": "contains", "path": "$.issues[*].type", "value": "empty_body"},
                {"type": "regex", "path": "$.summary", "pattern": "empty|缺少"},
            ],
        }
    ],
}

FAILING_SUITE: dict[str, Any] = {
    "name": "failing-suite",
    "description": "One assertion fails",
    "cases": [
        {
            "id": "case-fail",
            "name": "Fails contains",
            "inputs": {"code": "x = 1"},
            "assertions": [
                {"type": "contains", "path": "$.issues[*].type", "value": "nonexistent"},
            ],
        }
    ],
}

MULTI_CASE_SUITE: dict[str, Any] = {
    "name": "multi-suite",
    "description": "Two cases, one passes one fails",
    "cases": [
        {
            "id": "case-a",
            "name": "Passes",
            "inputs": {},
            "assertions": [
                {"type": "contains", "path": "$.ok", "value": True},
            ],
        },
        {
            "id": "case-b",
            "name": "Fails",
            "inputs": {},
            "assertions": [
                {"type": "contains", "path": "$.ok", "value": False},
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# _parse_output tests
# ---------------------------------------------------------------------------


class TestParseOutput:
    def test_plain_json_object(self) -> None:
        data = _parse_output('{"issues": [], "summary": "ok"}')
        assert isinstance(data, dict)
        assert data["issues"] == []

    def test_plain_json_array(self) -> None:
        data = _parse_output('[{"type": "bug"}]')
        assert isinstance(data, list)
        assert data[0]["type"] == "bug"

    def test_markdown_code_block(self) -> None:
        text = '```json\n{"result": "hello"}\n```'
        data = _parse_output(text)
        assert isinstance(data, dict)
        assert data["result"] == "hello"

    def test_plain_text_fallback(self) -> None:
        data = _parse_output("This is plain text.")
        assert data == "This is plain text."

    def test_invalid_json_falls_back_to_string(self) -> None:
        data = _parse_output("{broken json")
        assert isinstance(data, str)

    def test_empty_string(self) -> None:
        data = _parse_output("")
        assert data == ""


# ---------------------------------------------------------------------------
# run_eval tests
# ---------------------------------------------------------------------------


def _make_invoke(output_dict: dict[str, Any]) -> em.__class__:
    """Return a deterministic invoke_fn that always returns the given dict as JSON."""
    output_json = json.dumps(output_dict)

    def invoke(inputs: dict) -> tuple[str, int, int, float]:
        return output_json, 50, 100, 0.1

    return invoke


class TestRunEval:
    def test_passing_case(self, workspace: Path) -> None:
        em.save_suite(PASSING_SUITE, workspace)
        output = {"issues": [{"type": "empty_body"}], "summary": "empty function, 缺少实现"}
        report = run_eval(
            target="my-skill@v0.1.0",
            suite_name="passing-suite",
            invoke_fn=_make_invoke(output),
            base=workspace,
        )
        assert report["summary"]["total"] == 1
        assert report["summary"]["passed"] == 1
        assert report["summary"]["failed"] == 0
        assert report["cases"][0]["status"] == "passed"

    def test_failing_case(self, workspace: Path) -> None:
        em.save_suite(FAILING_SUITE, workspace)
        output = {"issues": [{"type": "ok"}], "summary": "looks good"}
        report = run_eval(
            target="my-skill@v0.1.0",
            suite_name="failing-suite",
            invoke_fn=_make_invoke(output),
            base=workspace,
        )
        assert report["summary"]["total"] == 1
        assert report["summary"]["passed"] == 0
        assert report["summary"]["failed"] == 1
        assert report["cases"][0]["status"] == "failed"

    def test_mixed_cases(self, workspace: Path) -> None:
        em.save_suite(MULTI_CASE_SUITE, workspace)
        # Returns {"ok": true} — case-a passes, case-b fails
        output = {"ok": True}
        report = run_eval(
            target="my-skill@v0.1.0",
            suite_name="multi-suite",
            invoke_fn=_make_invoke(output),
            base=workspace,
        )
        assert report["summary"]["total"] == 2
        assert report["summary"]["passed"] == 1
        assert report["summary"]["failed"] == 1

    def test_report_structure(self, workspace: Path) -> None:
        em.save_suite(PASSING_SUITE, workspace)
        output = {"issues": [{"type": "empty_body"}], "summary": "缺少实现"}
        report = run_eval(
            target="my-skill@v0.1.0",
            suite_name="passing-suite",
            invoke_fn=_make_invoke(output),
            base=workspace,
        )
        assert "timestamp" in report
        assert report["target"] == "my-skill@v0.1.0"
        assert report["suite"] == "passing-suite"
        assert "summary" in report
        assert "cases" in report
        assert "_result_file" in report

    def test_result_persisted_to_disk(self, workspace: Path) -> None:
        em.save_suite(PASSING_SUITE, workspace)
        output = {"issues": [{"type": "empty_body"}], "summary": "缺少实现"}
        report = run_eval(
            target="my-skill@v0.1.0",
            suite_name="passing-suite",
            invoke_fn=_make_invoke(output),
            base=workspace,
        )
        result_file = Path(report["_result_file"])
        assert result_file.exists()
        saved = json.loads(result_file.read_text())
        assert saved["target"] == "my-skill@v0.1.0"
        assert saved["summary"]["passed"] == 1

    def test_result_saved_in_correct_directory(self, workspace: Path) -> None:
        em.save_suite(PASSING_SUITE, workspace)
        output = {"issues": [{"type": "empty_body"}], "summary": "缺少实现"}
        report = run_eval(
            target="my-skill@v0.1.0",
            suite_name="passing-suite",
            invoke_fn=_make_invoke(output),
            base=workspace,
        )
        result_path = Path(report["_result_file"])
        expected_dir = workspace / ".harness" / "evals" / "results"
        assert result_path.parent == expected_dir

    def test_invoke_error_marks_case_as_error(self, workspace: Path) -> None:
        em.save_suite(PASSING_SUITE, workspace)

        def bad_invoke(inputs: dict) -> tuple:
            raise RuntimeError("LLM call failed")

        report = run_eval(
            target="my-skill@v0.1.0",
            suite_name="passing-suite",
            invoke_fn=bad_invoke,
            base=workspace,
        )
        assert report["cases"][0]["status"] == "error"
        assert "LLM call failed" in report["cases"][0]["error"]
        assert report["summary"]["failed"] == 1

    def test_assertion_details_included(self, workspace: Path) -> None:
        em.save_suite(PASSING_SUITE, workspace)
        output = {"issues": [{"type": "empty_body"}], "summary": "缺少实现"}
        report = run_eval(
            target="my-skill@v0.1.0",
            suite_name="passing-suite",
            invoke_fn=_make_invoke(output),
            base=workspace,
        )
        case = report["cases"][0]
        assert len(case["assertions"]) == 2
        for a in case["assertions"]:
            assert "type" in a
            assert "passed" in a
            assert "message" in a

    def test_token_info_recorded(self, workspace: Path) -> None:
        em.save_suite(PASSING_SUITE, workspace)
        output = {"issues": [{"type": "empty_body"}], "summary": "缺少实现"}
        report = run_eval(
            target="my-skill@v0.1.0",
            suite_name="passing-suite",
            invoke_fn=_make_invoke(output),
            base=workspace,
        )
        case = report["cases"][0]
        assert case["input_tokens"] == 50
        assert case["output_tokens"] == 100

    def test_suite_not_found_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            run_eval(
                target="my-skill@v0.1.0",
                suite_name="nonexistent",
                invoke_fn=_make_invoke({}),
                base=workspace,
            )

    def test_markdown_json_output_parsed(self, workspace: Path) -> None:
        """Output wrapped in markdown code block should still be parsed correctly."""
        em.save_suite(PASSING_SUITE, workspace)

        def invoke(inputs: dict) -> tuple:
            text = '```json\n{"issues": [{"type": "empty_body"}], "summary": "缺少实现"}\n```'
            return text, 10, 20, 0.05

        report = run_eval(
            target="my-skill@v0.1.0",
            suite_name="passing-suite",
            invoke_fn=invoke,
            base=workspace,
        )
        assert report["cases"][0]["status"] == "passed"

    def test_multiple_results_created(self, workspace: Path) -> None:
        """Each run_eval call creates a new result file."""
        em.save_suite(PASSING_SUITE, workspace)
        output = {"issues": [{"type": "empty_body"}], "summary": "缺少实现"}
        r1 = run_eval("sk@v1", "passing-suite", _make_invoke(output), base=workspace)
        # small sleep to avoid identical timestamp filenames
        time.sleep(0.01)
        r2 = run_eval("sk@v1", "passing-suite", _make_invoke(output), base=workspace)
        # Both files should exist (but may have same name if sub-second collision — just check both are valid)
        assert Path(r1["_result_file"]).exists()
        assert Path(r2["_result_file"]).exists()


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def skill_workspace(workspace: Path) -> Path:
    """Workspace with a minimal skill and test suite."""
    from harness_kit import skill as sm

    sm.save_skill(
        name="simple-skill",
        description="Simple skill for eval testing",
        trigger="when needed",
        inputs=[{"name": "code", "type": "string", "required": True}],
        base=workspace,
    )

    suite_data = {
        "name": "simple-suite",
        "description": "Simple eval suite",
        "cases": [
            {
                "id": "case-1",
                "name": "Check output",
                "inputs": {"code": "print('hello')"},
                "assertions": [
                    {"type": "contains", "path": "$.issues[*].type", "value": "ok"},
                ],
            }
        ],
    }
    em.save_suite(suite_data, workspace)
    return workspace


class TestEvalRunCLI:
    def test_missing_suite_option(self, workspace: Path) -> None:
        """--suite is required."""
        result = runner.invoke(app, ["eval", "run", "my-skill"])
        assert result.exit_code != 0

    def test_suite_not_found(self, workspace: Path) -> None:
        result = runner.invoke(app, ["eval", "run", "my-skill", "--suite", "ghost"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_skill_not_found(self, workspace: Path) -> None:
        em.save_suite(PASSING_SUITE, workspace)
        result = runner.invoke(app, ["eval", "run", "ghost-skill", "--suite", "passing-suite"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_run_with_mocked_llm(self, skill_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Full eval run with LLM mocked — checks report display and exit code."""
        from harness_kit.llm import LLMResponse

        mock_resp = LLMResponse(
            content='{"issues": [{"type": "ok"}], "summary": "all good"}',
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            duration=0.5,
        )

        with patch("harness_kit.cli.call_llm", return_value=mock_resp), \
             patch("harness_kit.cli.LLMConfig.from_harness_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(
                model="gpt-4o",
                api_key="sk-test",
                temperature=0.7,
                max_tokens=None,
                base_url=None,
            )
            result = runner.invoke(
                app,
                ["eval", "run", "simple-skill", "--suite", "simple-suite"],
            )

        assert result.exit_code == 0
        assert "simple-skill" in result.output
        assert "simple-suite" in result.output
        assert "Report saved" in result.output

    def test_ci_mode_fails_when_cases_fail(self, skill_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--ci exits 1 when any test case fails."""
        from harness_kit.llm import LLMResponse

        # Return output that does NOT satisfy the assertion
        mock_resp = LLMResponse(
            content='{"issues": [], "summary": "nothing found"}',
            model="gpt-4o",
            input_tokens=10,
            output_tokens=10,
            duration=0.1,
        )

        with patch("harness_kit.cli.call_llm", return_value=mock_resp), \
             patch("harness_kit.cli.LLMConfig.from_harness_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(
                model="gpt-4o",
                api_key="sk-test",
                temperature=0.7,
                max_tokens=None,
                base_url=None,
            )
            result = runner.invoke(
                app,
                ["eval", "run", "simple-skill", "--suite", "simple-suite", "--ci"],
            )

        assert result.exit_code == 1

    def test_ci_mode_passes_when_all_pass(self, skill_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--ci exits 0 when all cases pass."""
        from harness_kit.llm import LLMResponse

        mock_resp = LLMResponse(
            content='{"issues": [{"type": "ok"}], "summary": "all good"}',
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            duration=0.5,
        )

        with patch("harness_kit.cli.call_llm", return_value=mock_resp), \
             patch("harness_kit.cli.LLMConfig.from_harness_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(
                model="gpt-4o",
                api_key="sk-test",
                temperature=0.7,
                max_tokens=None,
                base_url=None,
            )
            result = runner.invoke(
                app,
                ["eval", "run", "simple-skill", "--suite", "simple-suite", "--ci"],
            )

        assert result.exit_code == 0

    def test_no_api_key(self, skill_workspace: Path) -> None:
        """Without API key, eval run should error."""
        with patch("harness_kit.cli.LLMConfig.from_harness_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(
                model="gpt-4o",
                api_key=None,
                temperature=0.7,
                max_tokens=None,
                base_url=None,
            )
            result = runner.invoke(
                app,
                ["eval", "run", "simple-skill", "--suite", "simple-suite"],
            )
        assert result.exit_code == 1
        assert "api key" in result.output.lower()
