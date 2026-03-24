"""Tests for Phase 2.3: Skill independent execution — LLM client, call logger, skill run."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit import skill as sm
from harness_kit import prompt as pm
from harness_kit import rule as rm
from harness_kit.llm import LLMConfig, LLMResponse, build_messages
from harness_kit import call_logger as cl

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
def skill_with_prompt(workspace: Path) -> Path:
    """Workspace with a simple skill that references a system prompt."""
    pm.save_prompt(
        name="sys-prompt",
        content="You are a helpful assistant. Language: {{language}}",
        description="System prompt",
        base=workspace,
    )
    pm.save_prompt(
        name="user-prompt",
        content="Please review the following code:\n{{code}}",
        description="User prompt",
        base=workspace,
    )
    sm.save_skill(
        name="code-reviewer",
        description="Reviews code",
        trigger="When code needs review",
        inputs=[
            {"name": "code", "type": "string", "required": True},
            {"name": "language", "type": "string", "default": "auto"},
        ],
        outputs=[{"name": "issues", "type": "array"}],
        assets={
            "prompts": {
                "system": "sys-prompt",
                "user": "user-prompt",
            }
        },
        base=workspace,
    )
    return workspace


@pytest.fixture()
def skill_with_hard_rule(workspace: Path) -> Path:
    """Workspace with a skill that has a hard rule."""
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
        description="Strict reviewer with hard rules",
        trigger="Review strictly",
        inputs=[{"name": "text", "type": "string", "required": True}],
        outputs=[{"name": "result", "type": "string"}],
        assets={"rules": ["no-speculation"]},
        base=workspace,
    )
    return workspace


# ---------------------------------------------------------------------------
# LLMConfig tests
# ---------------------------------------------------------------------------


class TestLLMConfig:
    def test_defaults(self) -> None:
        cfg = LLMConfig()
        assert cfg.model == "gpt-4o"
        assert cfg.temperature == 0.7
        assert cfg.base_url is None
        assert cfg.api_key is None

    def test_from_harness_config_model(self) -> None:
        harness_cfg = {"default_model": "claude-3-5-sonnet", "api_key": "${MY_KEY}"}
        cfg = LLMConfig.from_harness_config(harness_cfg)
        assert cfg.model == "claude-3-5-sonnet"

    def test_from_harness_config_reads_env_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MY_API_KEY", "sk-test-123")
        harness_cfg = {"default_model": "gpt-4o", "api_key": "${MY_API_KEY}"}
        cfg = LLMConfig.from_harness_config(harness_cfg)
        assert cfg.api_key == "sk-test-123"

    def test_from_harness_config_override_model(self) -> None:
        harness_cfg = {"default_model": "gpt-4o"}
        cfg = LLMConfig.from_harness_config(harness_cfg, overrides={"model": "gpt-4o-mini"})
        assert cfg.model == "gpt-4o-mini"

    def test_from_harness_config_base_url_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_BASE_URL", "https://custom.api.com/v1")
        harness_cfg = {"default_model": "gpt-4o"}
        cfg = LLMConfig.from_harness_config(harness_cfg)
        assert cfg.base_url == "https://custom.api.com/v1"

    def test_from_harness_config_base_url_from_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        harness_cfg = {"default_model": "gpt-4o", "base_url": "https://my-proxy.com/v1"}
        cfg = LLMConfig.from_harness_config(harness_cfg)
        assert cfg.base_url == "https://my-proxy.com/v1"

    def test_from_harness_config_missing_key_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        harness_cfg = {"default_model": "gpt-4o", "api_key": "${OPENAI_API_KEY}"}
        cfg = LLMConfig.from_harness_config(harness_cfg)
        assert cfg.api_key is None


# ---------------------------------------------------------------------------
# build_messages tests
# ---------------------------------------------------------------------------


class TestBuildMessages:
    def test_system_and_user_messages(self) -> None:
        skill_data = {"inputs": [], "assets": {}}
        rendered = {
            "system": "You are a code reviewer.",
            "user": "Review this code: {{code}}",
            "context": "",
            "rules": "",
            "schemas": "",
        }
        msgs = build_messages(skill_data, rendered, vars={"code": "def foo(): pass"})
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert "code reviewer" in msgs[0]["content"]
        assert msgs[1]["role"] == "user"
        assert "def foo(): pass" in msgs[1]["content"]

    def test_no_system_prompt(self) -> None:
        skill_data = {"inputs": [], "assets": {}}
        rendered = {"system": "", "user": "Hello {{name}}", "context": "", "rules": "", "schemas": ""}
        msgs = build_messages(skill_data, rendered, vars={"name": "World"})
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert "World" in msgs[0]["content"]

    def test_soft_rules_injected_into_system(self) -> None:
        skill_data = {"inputs": [], "assets": {}}
        rendered = {
            "system": "You are helpful.",
            "user": "Hi",
            "context": "",
            "rules": "[soft] no-fluff: Keep responses concise\n[hard] no-lies: No lies",
            "schemas": "",
        }
        msgs = build_messages(skill_data, rendered, vars={})
        system_content = msgs[0]["content"]
        assert "规则：" in system_content
        assert "concise" in system_content or "Keep responses" in system_content
        # hard rules should NOT be injected
        assert "no-lies" not in system_content

    def test_context_appended_to_user(self) -> None:
        skill_data = {"inputs": [], "assets": {}}
        rendered = {
            "system": "",
            "user": "Review this",
            "context": "Context: Python 3.10",
            "rules": "",
            "schemas": "",
        }
        msgs = build_messages(skill_data, rendered, vars={})
        user_content = msgs[0]["content"]
        assert "Review this" in user_content
        assert "Context: Python 3.10" in user_content

    def test_vars_only_fallback(self) -> None:
        skill_data = {"inputs": [], "assets": {}}
        rendered = {"system": "", "user": "", "context": "", "rules": "", "schemas": ""}
        msgs = build_messages(skill_data, rendered, vars={"key": "value"})
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert "key: value" in msgs[0]["content"]

    def test_empty_renders_no_messages(self) -> None:
        skill_data = {"inputs": [], "assets": {}}
        rendered = {"system": "", "user": "", "context": "", "rules": "", "schemas": ""}
        msgs = build_messages(skill_data, rendered, vars={})
        assert len(msgs) == 0


# ---------------------------------------------------------------------------
# call_llm tests (mocked)
# ---------------------------------------------------------------------------


class TestCallLlm:
    def _make_mock_response(self, content: str = "Hello!", model: str = "gpt-4o") -> MagicMock:
        usage = MagicMock()
        usage.prompt_tokens = 10
        usage.completion_tokens = 5
        choice = MagicMock()
        choice.message.content = content
        choice.finish_reason = "stop"
        response = MagicMock()
        response.choices = [choice]
        response.usage = usage
        response.model = model
        response.id = "chatcmpl-test"
        return response

    def test_non_streaming_returns_llm_response(self) -> None:
        from harness_kit.llm import call_llm

        cfg = LLMConfig(model="gpt-4o", api_key="sk-test")
        messages = [{"role": "user", "content": "Hello"}]
        mock_resp = self._make_mock_response("Hi there!")

        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_resp

            result = call_llm(messages, cfg, stream=False)

        assert isinstance(result, LLMResponse)
        assert result.content == "Hi there!"
        assert result.input_tokens == 10
        assert result.output_tokens == 5
        assert result.finish_reason == "stop"

    def test_non_streaming_passes_correct_args(self) -> None:
        from harness_kit.llm import call_llm

        cfg = LLMConfig(model="gpt-4o-mini", api_key="sk-test", temperature=0.3)
        messages = [{"role": "system", "content": "You are helpful."}, {"role": "user", "content": "Hi"}]
        mock_resp = self._make_mock_response()

        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_resp

            call_llm(messages, cfg, stream=False)

            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs["model"] == "gpt-4o-mini"
            assert call_kwargs["temperature"] == 0.3
            assert call_kwargs["messages"] == messages

    def test_base_url_passed_to_client(self) -> None:
        from harness_kit.llm import call_llm

        cfg = LLMConfig(model="gpt-4o", api_key="sk-test", base_url="https://custom.example.com/v1")
        messages = [{"role": "user", "content": "Hi"}]
        mock_resp = self._make_mock_response()

        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_resp

            call_llm(messages, cfg, stream=False)

            client_kwargs = mock_openai_cls.call_args[1]
            assert client_kwargs["base_url"] == "https://custom.example.com/v1"
            assert client_kwargs["api_key"] == "sk-test"

    def test_streaming_yields_chunks(self) -> None:
        from harness_kit.llm import call_llm

        cfg = LLMConfig(model="gpt-4o", api_key="sk-test")
        messages = [{"role": "user", "content": "Hi"}]

        def make_chunk(text: str | None, finish: str | None = None) -> MagicMock:
            chunk = MagicMock()
            delta = MagicMock()
            delta.content = text
            choice = MagicMock()
            choice.delta = delta
            choice.finish_reason = finish
            chunk.choices = [choice]
            chunk.model = "gpt-4o"
            return chunk

        chunks = [make_chunk("Hello"), make_chunk(", "), make_chunk("World"), make_chunk(None, "stop")]

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=iter(chunks))
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)

        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_stream_ctx

            gen = call_llm(messages, cfg, stream=True)
            collected = list(gen)

        assert "Hello" in collected
        assert ", " in collected
        assert "World" in collected

    def test_missing_openai_raises_import_error(self) -> None:
        from harness_kit.llm import call_llm
        import sys

        cfg = LLMConfig(model="gpt-4o", api_key="sk-test")
        messages = [{"role": "user", "content": "Hi"}]

        # Hide openai module
        with patch.dict(sys.modules, {"openai": None}):
            with pytest.raises(ImportError, match="openai"):
                call_llm(messages, cfg, stream=False)


# ---------------------------------------------------------------------------
# call_logger tests
# ---------------------------------------------------------------------------


class TestCallLogger:
    def test_log_call_creates_file(self, workspace: Path) -> None:
        cl.log_call(
            skill="test-skill",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            duration=1.23,
            status="success",
            base=workspace,
        )
        log_file = workspace / ".harness" / "logs" / "calls.jsonl"
        assert log_file.exists()

    def test_log_call_correct_fields(self, workspace: Path) -> None:
        cl.log_call(
            skill="my-skill",
            model="gpt-4o-mini",
            input_tokens=200,
            output_tokens=80,
            duration=2.5,
            status="success",
            inputs={"lang": "python"},
            output="Some output text",
            base=workspace,
        )
        log_file = workspace / ".harness" / "logs" / "calls.jsonl"
        record = json.loads(log_file.read_text().strip())
        assert record["skill"] == "my-skill"
        assert record["model"] == "gpt-4o-mini"
        assert record["input_tokens"] == 200
        assert record["output_tokens"] == 80
        assert record["total_tokens"] == 280
        assert record["duration"] == 2.5
        assert record["status"] == "success"
        assert record["inputs"]["lang"] == "python"
        assert "Some output" in record["output_preview"]
        assert record["type"] == "llm_call"
        assert "timestamp" in record

    def test_log_call_error_status(self, workspace: Path) -> None:
        cl.log_call(
            skill="failing-skill",
            model="gpt-4o",
            input_tokens=0,
            output_tokens=0,
            duration=0.0,
            status="error",
            error="API timeout",
            base=workspace,
        )
        log_file = workspace / ".harness" / "logs" / "calls.jsonl"
        record = json.loads(log_file.read_text().strip())
        assert record["status"] == "error"
        assert record["error"] == "API timeout"

    def test_log_call_appends_multiple_records(self, workspace: Path) -> None:
        for i in range(3):
            cl.log_call(
                skill=f"skill-{i}",
                model="gpt-4o",
                input_tokens=i * 10,
                output_tokens=i * 5,
                duration=float(i),
                base=workspace,
            )
        log_file = workspace / ".harness" / "logs" / "calls.jsonl"
        lines = [l for l in log_file.read_text().splitlines() if l.strip()]
        assert len(lines) == 3

    def test_log_call_output_preview_truncated(self, workspace: Path) -> None:
        long_output = "x" * 300
        cl.log_call(
            skill="s",
            model="gpt-4o",
            input_tokens=1,
            output_tokens=1,
            duration=0.1,
            output=long_output,
            base=workspace,
        )
        log_file = workspace / ".harness" / "logs" / "calls.jsonl"
        record = json.loads(log_file.read_text().strip())
        assert len(record["output_preview"]) <= 205  # 200 + "..."
        assert record["output_preview"].endswith("...")

    def test_tail_logs_empty(self, workspace: Path) -> None:
        records = cl.tail_logs(n=10, base=workspace)
        assert records == []

    def test_tail_logs_returns_last_n(self, workspace: Path) -> None:
        for i in range(5):
            cl.log_call(skill=f"s{i}", model="gpt-4o", input_tokens=i, output_tokens=i, duration=0.1, base=workspace)
        records = cl.tail_logs(n=3, base=workspace)
        assert len(records) == 3
        assert records[-1]["skill"] == "s4"

    def test_search_logs_by_skill(self, workspace: Path) -> None:
        cl.log_call(skill="alpha", model="gpt-4o", input_tokens=1, output_tokens=1, duration=0.1, base=workspace)
        cl.log_call(skill="beta", model="gpt-4o", input_tokens=2, output_tokens=2, duration=0.2, base=workspace)
        cl.log_call(skill="alpha", model="gpt-4o", input_tokens=3, output_tokens=3, duration=0.3, base=workspace)
        results = cl.search_logs(skill="alpha", base=workspace)
        assert len(results) == 2
        assert all(r["skill"] == "alpha" for r in results)

    def test_search_logs_by_status(self, workspace: Path) -> None:
        cl.log_call(skill="s", model="gpt-4o", input_tokens=1, output_tokens=1, duration=0.1, status="success", base=workspace)
        cl.log_call(skill="s", model="gpt-4o", input_tokens=1, output_tokens=1, duration=0.1, status="error", base=workspace)
        results = cl.search_logs(status="error", base=workspace)
        assert len(results) == 1
        assert results[0]["status"] == "error"


# ---------------------------------------------------------------------------
# CLI skill run tests
# ---------------------------------------------------------------------------


class TestCliSkillRun:
    def test_run_dry_run_shows_messages(self, skill_with_prompt: Path) -> None:
        result = runner.invoke(app, ["skill", "run", "code-reviewer", "--var", "code=def foo(): pass", "--dry-run"])
        assert result.exit_code == 0
        assert "dry-run" in result.output.lower() or "Assembled Messages" in result.output

    def test_run_dry_run_no_api_key_needed(self, skill_with_prompt: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = runner.invoke(app, ["skill", "run", "code-reviewer", "--var", "code=hello", "--dry-run"])
        assert result.exit_code == 0

    def test_run_missing_required_input_fails(self, skill_with_prompt: Path) -> None:
        result = runner.invoke(app, ["skill", "run", "code-reviewer"])
        # 'code' is required
        assert result.exit_code != 0
        assert "code" in result.output.lower() or "Missing" in result.output or "required" in result.output.lower()

    def test_run_invalid_var_format(self, skill_with_prompt: Path) -> None:
        result = runner.invoke(app, ["skill", "run", "code-reviewer", "--var", "badformat"])
        assert result.exit_code != 0

    def test_run_no_api_key_fails(self, skill_with_prompt: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = runner.invoke(app, ["skill", "run", "code-reviewer", "--var", "code=hello"])
        assert result.exit_code != 0
        assert "API key" in result.output or "api_key" in result.output

    def test_run_skill_not_found(self, workspace: Path) -> None:
        result = runner.invoke(app, ["skill", "run", "nonexistent-skill", "--var", "x=y"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "nonexistent" in result.output

    def test_run_calls_llm_and_logs(self, skill_with_prompt: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Full integration test with mocked OpenAI client."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
        monkeypatch.chdir(skill_with_prompt)

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 50
        mock_usage.completion_tokens = 30
        mock_choice = MagicMock()
        mock_choice.message.content = "Code looks good!"
        mock_choice.finish_reason = "stop"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage
        mock_response.model = "gpt-4o"
        mock_response.id = "test-id"

        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = runner.invoke(app, ["skill", "run", "code-reviewer", "--var", "code=def foo(): pass"])

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        assert "Code looks good!" in result.output

        # Verify log was written
        log_file = skill_with_prompt / ".harness" / "logs" / "calls.jsonl"
        assert log_file.exists()
        record = json.loads(log_file.read_text().strip())
        assert record["skill"] == "code-reviewer"
        assert record["status"] == "success"

    def test_run_hard_rule_violation_strict_fails(
        self, skill_with_hard_rule: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
        monkeypatch.chdir(skill_with_hard_rule)

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 20
        mock_choice = MagicMock()
        mock_choice.message.content = "我猜测这是一个 bug。"  # Triggers hard rule
        mock_choice.finish_reason = "stop"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage
        mock_response.model = "gpt-4o"
        mock_response.id = "test-id"

        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = runner.invoke(
                app,
                ["skill", "run", "strict-reviewer", "--var", "text=hello", "--check-rules", "strict"],
            )

        assert result.exit_code != 0
        assert "Rule Violations" in result.output or "no-speculation" in result.output

    def test_run_hard_rule_violation_lenient_continues(
        self, skill_with_hard_rule: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
        monkeypatch.chdir(skill_with_hard_rule)

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 20
        mock_choice = MagicMock()
        mock_choice.message.content = "我猜测这是一个 bug。"  # Triggers hard rule
        mock_choice.finish_reason = "stop"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage
        mock_response.model = "gpt-4o"
        mock_response.id = "test-id"

        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = runner.invoke(
                app,
                ["skill", "run", "strict-reviewer", "--var", "text=hello", "--check-rules", "lenient"],
            )

        # Lenient: shows warning but does NOT fail
        assert result.exit_code == 0
        assert "Rule Violations" in result.output or "no-speculation" in result.output


# ---------------------------------------------------------------------------
# CLI logs tests
# ---------------------------------------------------------------------------


class TestCliLogs:
    def test_logs_tail_empty(self, workspace: Path) -> None:
        result = runner.invoke(app, ["logs", "tail"])
        assert result.exit_code == 0
        assert "No call logs" in result.output or "call logs" in result.output.lower()

    def test_logs_tail_with_records(self, workspace: Path) -> None:
        for i in range(3):
            cl.log_call(
                skill=f"skill-{i}",
                model="gpt-4o",
                input_tokens=i * 10,
                output_tokens=i * 5,
                duration=float(i) * 0.5,
                base=workspace,
            )
        result = runner.invoke(app, ["logs", "tail", "--n", "5"])
        assert result.exit_code == 0
        assert "skill-0" in result.output or "skill-2" in result.output

    def test_logs_search_by_skill(self, workspace: Path) -> None:
        cl.log_call(skill="alpha", model="gpt-4o", input_tokens=1, output_tokens=1, duration=0.1, base=workspace)
        cl.log_call(skill="beta", model="gpt-4o", input_tokens=2, output_tokens=2, duration=0.2, base=workspace)
        result = runner.invoke(app, ["logs", "search", "--skill", "alpha"])
        assert result.exit_code == 0
        assert "alpha" in result.output
        assert "beta" not in result.output

    def test_logs_search_no_results(self, workspace: Path) -> None:
        result = runner.invoke(app, ["logs", "search", "--skill", "nonexistent"])
        assert result.exit_code == 0
        assert "No matching" in result.output or "No call logs" in result.output.lower()
