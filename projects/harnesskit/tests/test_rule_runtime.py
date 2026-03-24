"""Tests for Phase 2.4: Rule 运行时检查 — runtime rule checking, violation logging, stats."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit import skill as sm
from harness_kit import prompt as pm
from harness_kit import rule as rm
from harness_kit import call_logger as cl

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


@pytest.fixture()
def hard_rule_workspace(workspace: Path) -> Path:
    """Workspace with a hard rule and a skill referencing it."""
    rm.save_rule(
        name="no-speculation",
        rule_type="hard",
        description="No speculative content",
        check_type="regex",
        pattern=r"我猜测|可能是",
        fix_hint="Remove speculative language",
        base=workspace,
    )
    sm.save_skill(
        name="strict-reviewer",
        description="Strict reviewer with hard rule",
        trigger="Review strictly",
        inputs=[{"name": "text", "type": "string", "required": True}],
        outputs=[{"name": "result", "type": "string"}],
        assets={"rules": ["no-speculation"]},
        base=workspace,
    )
    return workspace


@pytest.fixture()
def soft_rule_workspace(workspace: Path) -> Path:
    """Workspace with a soft rule and a skill referencing it."""
    rm.save_rule(
        name="be-concise",
        rule_type="soft",
        description="Keep responses brief and to the point",
        check_type="regex",
        pattern=r"很长的废话",
        fix_hint="Remove filler text",
        base=workspace,
    )
    pm.save_prompt(
        name="sys-prompt",
        content="You are a helpful reviewer.",
        description="System prompt",
        base=workspace,
    )
    sm.save_skill(
        name="soft-reviewer",
        description="Reviewer with soft rule",
        trigger="Review",
        inputs=[{"name": "text", "type": "string", "required": True}],
        outputs=[{"name": "result", "type": "string"}],
        assets={
            "prompts": {"system": "sys-prompt"},
            "rules": ["be-concise"],
        },
        base=workspace,
    )
    return workspace


def _make_mock_openai(content: str, model: str = "gpt-4o") -> tuple[MagicMock, MagicMock]:
    """Build a mock openai.OpenAI client that returns the given content."""
    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 20
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    response.model = model
    response.id = "test-id"

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = response
    return mock_client, response


# ---------------------------------------------------------------------------
# Tests: hard rule runtime interception
# ---------------------------------------------------------------------------


class TestHardRuleRuntimeCheck:
    def test_hard_rule_triggers_on_violation(self, hard_rule_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Hard rule should trigger when LLM output matches pattern."""
        result = rm.check_rule_by_name("no-speculation", "我猜测这是一个 bug。", base=hard_rule_workspace)
        assert result.triggered is True
        assert result.rule_type == "hard"
        assert "我猜测" in result.matches

    def test_hard_rule_does_not_trigger_on_clean_output(self, hard_rule_workspace: Path) -> None:
        """Hard rule should not trigger when output is clean."""
        result = rm.check_rule_by_name("no-speculation", "This is a definite bug.", base=hard_rule_workspace)
        assert result.triggered is False

    def test_strict_mode_fails_on_hard_violation(
        self, hard_rule_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """strict mode: exit code != 0 when hard rule is violated."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
        mock_client, _ = _make_mock_openai("我猜测这是一个 bug。")

        with patch("openai.OpenAI") as mock_cls:
            mock_cls.return_value = mock_client
            result = runner.invoke(
                app,
                ["skill", "run", "strict-reviewer", "--var", "text=hello", "--check-rules", "strict"],
            )

        assert result.exit_code != 0
        assert "Rule Violations" in result.output or "no-speculation" in result.output

    def test_lenient_mode_warns_but_exits_zero(
        self, hard_rule_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """lenient mode: shows warning but exit code == 0."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
        mock_client, _ = _make_mock_openai("我猜测这是一个 bug。")

        with patch("openai.OpenAI") as mock_cls:
            mock_cls.return_value = mock_client
            result = runner.invoke(
                app,
                ["skill", "run", "strict-reviewer", "--var", "text=hello", "--check-rules", "lenient"],
            )

        assert result.exit_code == 0
        assert "Rule Violations" in result.output or "no-speculation" in result.output

    def test_clean_output_no_violations_shown(
        self, hard_rule_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Clean LLM output should not show any Rule Violations section."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
        mock_client, _ = _make_mock_openai("The code looks correct.")

        with patch("openai.OpenAI") as mock_cls:
            mock_cls.return_value = mock_client
            result = runner.invoke(
                app,
                ["skill", "run", "strict-reviewer", "--var", "text=hello"],
            )

        assert result.exit_code == 0
        assert "Rule Violations" not in result.output

    def test_violation_shows_fix_hint(
        self, hard_rule_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Violation output should include the fix_hint."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
        mock_client, _ = _make_mock_openai("我猜测这是正确的。")

        with patch("openai.OpenAI") as mock_cls:
            mock_cls.return_value = mock_client
            result = runner.invoke(
                app,
                ["skill", "run", "strict-reviewer", "--var", "text=hello", "--check-rules", "lenient"],
            )

        assert "Remove speculative" in result.output or "fix_hint" in result.output or "no-speculation" in result.output


# ---------------------------------------------------------------------------
# Tests: violation logging
# ---------------------------------------------------------------------------


class TestViolationLogging:
    def test_strict_violation_logged_with_violations_field(
        self, hard_rule_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """In strict mode, violations are logged with structured violations field."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
        mock_client, _ = _make_mock_openai("我猜测这是一个 bug。")

        with patch("openai.OpenAI") as mock_cls:
            mock_cls.return_value = mock_client
            runner.invoke(
                app,
                ["skill", "run", "strict-reviewer", "--var", "text=hello", "--check-rules", "strict"],
            )

        log_file = hard_rule_workspace / ".harness" / "logs" / "calls.jsonl"
        assert log_file.exists()
        record = json.loads(log_file.read_text().strip())
        assert record["status"] == "rule_violation"
        assert "violations" in record
        assert len(record["violations"]) > 0
        assert record["violations"][0]["rule"] == "no-speculation"
        assert record["violations"][0]["type"] == "hard"
        assert record["violation_count"] == 1

    def test_lenient_violation_logged_with_violations_field(
        self, hard_rule_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """In lenient mode, violations are also logged with structured violations field."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
        mock_client, _ = _make_mock_openai("我猜测这是一个 bug。")

        with patch("openai.OpenAI") as mock_cls:
            mock_cls.return_value = mock_client
            runner.invoke(
                app,
                ["skill", "run", "strict-reviewer", "--var", "text=hello", "--check-rules", "lenient"],
            )

        log_file = hard_rule_workspace / ".harness" / "logs" / "calls.jsonl"
        assert log_file.exists()
        record = json.loads(log_file.read_text().strip())
        assert record["status"] == "rule_violation"
        assert "violations" in record
        assert record["violations"][0]["rule"] == "no-speculation"
        assert record["violation_count"] == 1

    def test_clean_output_logged_as_success_no_violations(
        self, hard_rule_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Clean output is logged as success with no violations field."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
        mock_client, _ = _make_mock_openai("The code looks correct.")

        with patch("openai.OpenAI") as mock_cls:
            mock_cls.return_value = mock_client
            runner.invoke(
                app,
                ["skill", "run", "strict-reviewer", "--var", "text=hello"],
            )

        log_file = hard_rule_workspace / ".harness" / "logs" / "calls.jsonl"
        assert log_file.exists()
        record = json.loads(log_file.read_text().strip())
        assert record["status"] == "success"
        assert "violations" not in record

    def test_violations_include_matches(
        self, hard_rule_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Logged violations should contain the actual matched strings."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
        mock_client, _ = _make_mock_openai("我猜测这是 bug，可能是问题。")

        with patch("openai.OpenAI") as mock_cls:
            mock_cls.return_value = mock_client
            runner.invoke(
                app,
                ["skill", "run", "strict-reviewer", "--var", "text=hello", "--check-rules", "lenient"],
            )

        log_file = hard_rule_workspace / ".harness" / "logs" / "calls.jsonl"
        record = json.loads(log_file.read_text().strip())
        matches = record["violations"][0]["matches"]
        assert "我猜测" in matches or "可能是" in matches


# ---------------------------------------------------------------------------
# Tests: call_logger violation_stats
# ---------------------------------------------------------------------------


class TestViolationStats:
    def test_violation_stats_empty_logs(self, workspace: Path) -> None:
        stats = cl.violation_stats(base=workspace)
        assert stats == {}

    def test_violation_stats_no_violations_in_logs(self, workspace: Path) -> None:
        cl.log_call(
            skill="s",
            model="gpt-4o",
            input_tokens=10,
            output_tokens=5,
            duration=0.5,
            status="success",
            base=workspace,
        )
        stats = cl.violation_stats(base=workspace)
        assert stats == {}

    def test_violation_stats_counts_correctly(self, workspace: Path) -> None:
        cl.log_call(
            skill="s",
            model="gpt-4o",
            input_tokens=10,
            output_tokens=5,
            duration=0.5,
            status="rule_violation",
            violations=[{"rule": "no-speculation", "type": "hard", "matches": ["我猜测"], "fix_hint": ""}],
            base=workspace,
        )
        cl.log_call(
            skill="s",
            model="gpt-4o",
            input_tokens=10,
            output_tokens=5,
            duration=0.5,
            status="rule_violation",
            violations=[{"rule": "no-speculation", "type": "hard", "matches": ["可能是"], "fix_hint": ""}],
            base=workspace,
        )
        cl.log_call(
            skill="s",
            model="gpt-4o",
            input_tokens=10,
            output_tokens=5,
            duration=0.5,
            status="rule_violation",
            violations=[
                {"rule": "no-speculation", "type": "hard", "matches": ["我猜测"], "fix_hint": ""},
                {"rule": "no-html", "type": "hard", "matches": ["<div>"], "fix_hint": ""},
            ],
            base=workspace,
        )
        stats = cl.violation_stats(base=workspace)
        assert stats["no-speculation"] == 3
        assert stats["no-html"] == 1

    def test_violation_stats_skips_success_records(self, workspace: Path) -> None:
        cl.log_call(
            skill="s",
            model="gpt-4o",
            input_tokens=1,
            output_tokens=1,
            duration=0.1,
            status="success",
            base=workspace,
        )
        cl.log_call(
            skill="s",
            model="gpt-4o",
            input_tokens=1,
            output_tokens=1,
            duration=0.1,
            status="rule_violation",
            violations=[{"rule": "my-rule", "type": "hard", "matches": ["x"], "fix_hint": ""}],
            base=workspace,
        )
        stats = cl.violation_stats(base=workspace)
        assert "my-rule" in stats
        assert stats["my-rule"] == 1


# ---------------------------------------------------------------------------
# Tests: rule stats CLI command
# ---------------------------------------------------------------------------


class TestRuleStatsCommand:
    def test_rule_stats_no_rules(self, workspace: Path) -> None:
        result = runner.invoke(app, ["rule", "stats"])
        assert result.exit_code == 0
        assert "No rules" in result.output or "stats" in result.output.lower()

    def test_rule_stats_shows_rules_with_zero_count(self, workspace: Path) -> None:
        rm.save_rule(
            name="no-speculation",
            rule_type="hard",
            description="No speculation",
            check_type="regex",
            pattern=r"我猜测",
            fix_hint="Remove it",
            base=workspace,
        )
        result = runner.invoke(app, ["rule", "stats"])
        assert result.exit_code == 0
        assert "no-speculation" in result.output
        assert "0" in result.output

    def test_rule_stats_shows_violation_count(self, workspace: Path) -> None:
        rm.save_rule(
            name="no-speculation",
            rule_type="hard",
            description="No speculation",
            check_type="regex",
            pattern=r"我猜测",
            fix_hint="Remove it",
            base=workspace,
        )
        # Log two violations
        cl.log_call(
            skill="s",
            model="gpt-4o",
            input_tokens=1,
            output_tokens=1,
            duration=0.1,
            status="rule_violation",
            violations=[{"rule": "no-speculation", "type": "hard", "matches": ["我猜测"], "fix_hint": ""}],
            base=workspace,
        )
        cl.log_call(
            skill="s",
            model="gpt-4o",
            input_tokens=1,
            output_tokens=1,
            duration=0.1,
            status="rule_violation",
            violations=[{"rule": "no-speculation", "type": "hard", "matches": ["我猜测"], "fix_hint": ""}],
            base=workspace,
        )
        result = runner.invoke(app, ["rule", "stats"])
        assert result.exit_code == 0
        assert "no-speculation" in result.output
        assert "2" in result.output

    def test_rule_stats_shows_total(self, workspace: Path) -> None:
        rm.save_rule(
            name="rule-a",
            rule_type="hard",
            description="Rule A",
            check_type="regex",
            pattern=r"bad",
            fix_hint="Fix it",
            base=workspace,
        )
        cl.log_call(
            skill="s",
            model="gpt-4o",
            input_tokens=1,
            output_tokens=1,
            duration=0.1,
            status="rule_violation",
            violations=[{"rule": "rule-a", "type": "hard", "matches": ["bad"], "fix_hint": ""}],
            base=workspace,
        )
        result = runner.invoke(app, ["rule", "stats"])
        assert result.exit_code == 0
        assert "Total violations" in result.output or "1" in result.output


# ---------------------------------------------------------------------------
# Tests: soft rule injection into system prompt
# ---------------------------------------------------------------------------


class TestSoftRuleInjection:
    def test_soft_rule_injected_in_dry_run(self, soft_rule_workspace: Path) -> None:
        """Soft rule description should appear in the assembled system prompt."""
        result = runner.invoke(
            app,
            ["skill", "run", "soft-reviewer", "--var", "text=hello", "--dry-run"],
        )
        assert result.exit_code == 0
        # Soft rule injected as "规则：..."
        assert "规则：" in result.output or "brief" in result.output or "be-concise" in result.output.lower()

    def test_soft_rule_not_in_hard_rule_output(self, hard_rule_workspace: Path) -> None:
        """Hard rules should NOT be injected into the system prompt."""
        result = runner.invoke(
            app,
            ["skill", "run", "strict-reviewer", "--var", "text=hello", "--dry-run"],
        )
        assert result.exit_code == 0
        # Hard rule should not appear as "规则：..." in system
        # (it's checked post-response, not injected)
        assert "规则：" not in result.output or "no-speculation" not in result.output.split("规则：")[1].split("\n")[0] if "规则：" in result.output else True
