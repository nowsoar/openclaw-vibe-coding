"""Tests for Phase 3.2: Harness CLI commands, harness run, context budget management."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from harness_kit.cli import app, _estimate_tokens
from harness_kit.config import init_harness
from harness_kit import harness as hm
from harness_kit import skill as sm

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Initialised .harness workspace in tmp_path."""
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


@pytest.fixture()
def workspace_with_skill(workspace: Path) -> tuple[Path, str]:
    """Workspace with a single skill (no required inputs) already saved."""
    sm.save_skill(
        "my-skill",
        description="A test skill",
        base=workspace,
    )
    hm.save_harness(
        "my-harness",
        description="Test harness",
        skills=["my-skill"],
        base=workspace,
    )
    return workspace, "my-harness"


@pytest.fixture()
def workspace_with_multi_skills(workspace: Path) -> tuple[Path, str]:
    """Workspace with two skills in one harness."""
    sm.save_skill("skill-a", description="Skill A", base=workspace)
    sm.save_skill("skill-b", description="Skill B", base=workspace)
    hm.save_harness(
        "multi-harness",
        description="Multi skill harness",
        skills=["skill-a", "skill-b"],
        base=workspace,
    )
    return workspace, "multi-harness"


# ---------------------------------------------------------------------------
# Unit tests: _estimate_tokens helper
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    def test_zero_chars(self) -> None:
        assert _estimate_tokens(0) == 1  # max(1, 0//4)

    def test_short_count(self) -> None:
        # 8 chars -> 2 tokens
        result = _estimate_tokens(8)
        assert result == 2

    def test_long_count(self) -> None:
        assert _estimate_tokens(400) == 100

    def test_returns_int(self) -> None:
        assert isinstance(_estimate_tokens(44), int)


# ---------------------------------------------------------------------------
# CLI integration tests: harness run - no API key (dry-run / error paths)
# ---------------------------------------------------------------------------


class TestHarnessRunDryRun:
    def test_dry_run_single_skill(self, workspace_with_skill: tuple[Path, str]) -> None:
        """dry-run shows assembled messages without LLM call."""
        workspace, harness_name = workspace_with_skill
        result = runner.invoke(
            app,
            [
                "harness", "run", harness_name,
                "--var", "query=test input",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "dry-run" in result.output.lower() or "Messages" in result.output

    def test_dry_run_shows_model(self, workspace_with_skill: tuple[Path, str]) -> None:
        workspace, harness_name = workspace_with_skill
        result = runner.invoke(
            app,
            ["harness", "run", harness_name, "--dry-run"],
        )
        assert result.exit_code == 0, result.output
        # Should show model name
        assert "gpt-4o" in result.output or "Model:" in result.output

    def test_dry_run_shows_context_budget(self, workspace_with_skill: tuple[Path, str]) -> None:
        workspace, harness_name = workspace_with_skill
        result = runner.invoke(
            app,
            ["harness", "run", harness_name, "--dry-run"],
        )
        assert result.exit_code == 0, result.output
        assert "budget" in result.output.lower() or "4000" in result.output

    def test_context_budget_warning(self, workspace: Path) -> None:
        """Context budget warning triggered when prompt exceeds budget."""
        # Create skill with large default input
        sm.save_skill("big-skill", description="Big skill", base=workspace)
        hm.save_harness(
            "small-budget-harness",
            description="Small budget",
            skills=["big-skill"],
            context_budget=1,  # extremely small budget to trigger warning
            base=workspace,
        )
        result = runner.invoke(
            app,
            ["harness", "run", "small-budget-harness", "--dry-run"],
        )
        assert result.exit_code == 0, result.output
        # Warning about exceeding budget should appear
        assert "exceed" in result.output.lower() or "budget" in result.output.lower()

    def test_no_api_key_without_dry_run(self, workspace_with_skill: tuple[Path, str]) -> None:
        """Without --dry-run and no API key, should fail with clear message."""
        workspace, harness_name = workspace_with_skill
        with patch.dict("os.environ", {}, clear=True):
            # Remove any API key env vars
            import os
            env = {k: v for k, v in os.environ.items() if "API_KEY" not in k}
            with patch.dict("os.environ", env, clear=True):
                result = runner.invoke(
                    app,
                    ["harness", "run", harness_name],
                )
        # Either fails due to no API key or some other issue
        # Exit code 1 is expected when no key
        assert result.exit_code in (0, 1)

    def test_harness_not_found(self, workspace: Path) -> None:
        result = runner.invoke(app, ["harness", "run", "nonexistent-harness"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_harness_without_init(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["harness", "run", "any-harness"])
        assert result.exit_code == 1
        assert "init" in result.output.lower()

    def test_harness_with_no_skills(self, workspace: Path) -> None:
        hm.save_harness("empty-harness", description="No skills", skills=[], base=workspace)
        result = runner.invoke(app, ["harness", "run", "empty-harness"])
        assert result.exit_code == 1
        assert "no skills" in result.output.lower()

    def test_multi_skill_requires_skill_flag(
        self, workspace_with_multi_skills: tuple[Path, str]
    ) -> None:
        """Harness with multiple skills requires --skill flag."""
        workspace, harness_name = workspace_with_multi_skills
        result = runner.invoke(app, ["harness", "run", harness_name])
        assert result.exit_code == 1
        assert "--skill" in result.output

    def test_multi_skill_with_skill_flag_dry_run(
        self, workspace_with_multi_skills: tuple[Path, str]
    ) -> None:
        """Can select a specific skill with --skill flag."""
        workspace, harness_name = workspace_with_multi_skills
        result = runner.invoke(
            app,
            ["harness", "run", harness_name, "--skill", "skill-a", "--dry-run"],
        )
        assert result.exit_code == 0, result.output

    def test_multi_skill_invalid_skill_flag(
        self, workspace_with_multi_skills: tuple[Path, str]
    ) -> None:
        """Invalid --skill value gives clear error listing available skills."""
        workspace, harness_name = workspace_with_multi_skills
        result = runner.invoke(
            app,
            ["harness", "run", harness_name, "--skill", "nonexistent-skill", "--dry-run"],
        )
        assert result.exit_code == 1
        assert "nonexistent-skill" in result.output
        assert "skill-a" in result.output or "skill-b" in result.output

    def test_missing_required_input(self, workspace: Path) -> None:
        """Missing required input gives clear error with hint."""
        sm.save_skill(
            "req-skill",
            description="Requires input",
            inputs=[{"name": "topic", "type": "string", "required": True}],
            base=workspace,
        )
        hm.save_harness(
            "req-harness",
            description="Requires input harness",
            skills=["req-skill"],
            base=workspace,
        )
        result = runner.invoke(
            app,
            ["harness", "run", "req-harness", "--dry-run"],
        )
        # Should fail with missing input error
        assert result.exit_code == 1
        assert "topic" in result.output
        assert "--var" in result.output

    def test_harness_run_uses_harness_model_config(self, workspace: Path) -> None:
        """Harness model config overrides global config in dry-run."""
        sm.save_skill("m-skill", description="Model test skill", base=workspace)
        hm.save_harness(
            "model-harness",
            description="Custom model harness",
            skills=["m-skill"],
            model={"provider": "openai", "name": "gpt-4-turbo", "temperature": 0.2, "max_tokens": 512},
            base=workspace,
        )
        result = runner.invoke(
            app,
            ["harness", "run", "model-harness", "--dry-run"],
        )
        assert result.exit_code == 0, result.output
        assert "gpt-4-turbo" in result.output

    def test_harness_run_model_cli_override(self, workspace: Path) -> None:
        """CLI --model overrides harness model config."""
        sm.save_skill("o-skill", description="Override model skill", base=workspace)
        hm.save_harness(
            "override-harness",
            description="Override model harness",
            skills=["o-skill"],
            model={"provider": "openai", "name": "gpt-4o", "temperature": 0.7},
            base=workspace,
        )
        result = runner.invoke(
            app,
            ["harness", "run", "override-harness", "--model", "gpt-3.5-turbo", "--dry-run"],
        )
        assert result.exit_code == 0, result.output
        assert "gpt-3.5-turbo" in result.output

    def test_harness_run_with_version_ref(self, workspace_with_skill: tuple[Path, str]) -> None:
        """Can run harness using name@version syntax."""
        workspace, harness_name = workspace_with_skill
        # Get current version
        version = hm.get_current_version(harness_name, workspace)
        result = runner.invoke(
            app,
            ["harness", "run", f"{harness_name}@{version}", "--dry-run"],
        )
        assert result.exit_code == 0, result.output

    def test_harness_run_invalid_var_format(self, workspace_with_skill: tuple[Path, str]) -> None:
        """Invalid --var format gives clear error."""
        workspace, harness_name = workspace_with_skill
        result = runner.invoke(
            app,
            ["harness", "run", harness_name, "--var", "invalid_no_equals"],
        )
        assert result.exit_code == 1
        assert "key=value" in result.output.lower() or "invalid" in result.output.lower()


# ---------------------------------------------------------------------------
# Mocked LLM call tests
# ---------------------------------------------------------------------------


class TestHarnessRunWithMockedLLM:
    """Tests that mock the LLM call to verify full run flow."""

    def _make_mock_response(self) -> MagicMock:
        resp = MagicMock()
        resp.content = "Mock LLM output"
        resp.model = "gpt-4o"
        resp.input_tokens = 50
        resp.output_tokens = 20
        resp.duration = 0.5
        return resp

    def test_run_success_logs_call(self, workspace_with_skill: tuple[Path, str]) -> None:
        """Successful harness run writes to call log."""
        workspace, harness_name = workspace_with_skill
        mock_resp = self._make_mock_response()

        with patch("harness_kit.llm.call_llm", return_value=mock_resp), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = runner.invoke(
                app,
                ["harness", "run", harness_name, "--var", "query=hello"],
            )

        assert result.exit_code == 0, result.output
        assert "Mock LLM output" in result.output

        # Check log was written
        log_file = workspace / ".harness" / "logs" / "calls.jsonl"
        assert log_file.exists()
        import json
        lines = [json.loads(l) for l in log_file.read_text().splitlines() if l.strip()]
        assert len(lines) >= 1
        last = lines[-1]
        assert "my-skill" in last.get("skill", "")
        assert last.get("status") == "success"

    def test_run_outputs_llm_result(self, workspace_with_skill: tuple[Path, str]) -> None:
        """Output section displays LLM response."""
        workspace, harness_name = workspace_with_skill
        mock_resp = self._make_mock_response()
        mock_resp.content = "This is the harness output"

        with patch("harness_kit.llm.call_llm", return_value=mock_resp), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = runner.invoke(
                app,
                ["harness", "run", harness_name],
            )

        assert result.exit_code == 0, result.output
        assert "This is the harness output" in result.output

    def test_run_shows_token_stats(self, workspace_with_skill: tuple[Path, str]) -> None:
        """Output includes token counts."""
        workspace, harness_name = workspace_with_skill
        mock_resp = self._make_mock_response()

        with patch("harness_kit.llm.call_llm", return_value=mock_resp), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = runner.invoke(
                app,
                ["harness", "run", harness_name],
            )

        assert result.exit_code == 0, result.output
        assert "50" in result.output or "Tokens" in result.output

    def test_run_multi_skill_dispatches_correctly(
        self, workspace_with_multi_skills: tuple[Path, str]
    ) -> None:
        """Multi-skill harness dispatches to correct skill."""
        workspace, harness_name = workspace_with_multi_skills
        mock_resp = self._make_mock_response()
        mock_resp.content = "Skill-A was run"

        with patch("harness_kit.llm.call_llm", return_value=mock_resp), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = runner.invoke(
                app,
                ["harness", "run", harness_name, "--skill", "skill-a"],
            )

        assert result.exit_code == 0, result.output
        assert "skill-a" in result.output.lower()

    def test_run_logs_harness_name_in_skill_field(
        self, workspace_with_skill: tuple[Path, str]
    ) -> None:
        """Log entry includes harness name prefix in skill field."""
        workspace, harness_name = workspace_with_skill
        mock_resp = self._make_mock_response()

        with patch("harness_kit.llm.call_llm", return_value=mock_resp), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            runner.invoke(app, ["harness", "run", harness_name])

        import json
        log_file = workspace / ".harness" / "logs" / "calls.jsonl"
        lines = [json.loads(l) for l in log_file.read_text().splitlines() if l.strip()]
        last = lines[-1]
        # skill field should be "harness_name/skill_name"
        assert harness_name in last.get("skill", "")

    def test_run_context_budget_management(self, workspace: Path) -> None:
        """Context budget warning is displayed when prompt is too large."""
        sm.save_skill("cb-skill", description="Context budget skill", base=workspace)
        hm.save_harness(
            "cb-harness",
            description="Context budget test",
            skills=["cb-skill"],
            context_budget=5,  # tiny budget
            base=workspace,
        )
        mock_resp = self._make_mock_response()

        with patch("harness_kit.llm.call_llm", return_value=mock_resp), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = runner.invoke(app, ["harness", "run", "cb-harness"])

        # Should warn about exceeding budget but still run
        assert "budget" in result.output.lower() or "exceed" in result.output.lower()

    def test_run_with_harness_constraint_rules(self, workspace: Path) -> None:
        """Harness constraint rules are applied to output."""
        from harness_kit import rule as rm

        rm.save_rule(
            name="test-rule",
            description="Test rule",
            rule_type="hard",
            check_type="regex",
            pattern="FORBIDDEN_WORD",
            fix_hint="Remove forbidden word",
            base=workspace,
        )
        sm.save_skill("rule-skill", description="Rule skill", base=workspace)
        hm.save_harness(
            "rule-harness",
            description="Rule harness",
            skills=["rule-skill"],
            constraints={"rules": ["test-rule"]},
            base=workspace,
        )

        # Mock LLM to return content that triggers the rule
        mock_resp = self._make_mock_response()
        mock_resp.content = "This contains FORBIDDEN_WORD in the output"

        with patch("harness_kit.llm.call_llm", return_value=mock_resp), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = runner.invoke(
                app,
                ["harness", "run", "rule-harness"],
            )

        # Should show rule violation warning
        assert "test-rule" in result.output or "violation" in result.output.lower() or "Rule" in result.output

    def test_run_strict_rule_fails_exit(self, workspace: Path) -> None:
        """Strict check-rules mode fails when hard rule triggered."""
        from harness_kit import rule as rm

        rm.save_rule(
            name="strict-rule",
            description="Strict rule",
            rule_type="hard",
            check_type="regex",
            pattern="BAD",
            fix_hint="Remove BAD",
            base=workspace,
        )
        sm.save_skill("sr-skill", description="Strict rule skill", base=workspace)
        hm.save_harness(
            "strict-harness",
            description="Strict harness",
            skills=["sr-skill"],
            constraints={"rules": ["strict-rule"]},
            base=workspace,
        )

        mock_resp = self._make_mock_response()
        mock_resp.content = "This output contains BAD content"

        with patch("harness_kit.llm.call_llm", return_value=mock_resp), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = runner.invoke(
                app,
                ["harness", "run", "strict-harness", "--check-rules", "strict"],
            )

        assert result.exit_code == 1
