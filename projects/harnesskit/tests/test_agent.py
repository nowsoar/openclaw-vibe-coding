"""Tests for Phase 3.4: Agent data model, CLI commands, and interactive REPL."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit import agent as am
from harness_kit import harness as hm

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_AGENT: dict = {
    "name": "code-assistant",
    "harness": "my-harness@v0.0.1",
    "identity": {
        "name": "代码助手",
        "description": "帮助你审查和改进代码",
    },
    "memory": {
        "scope": "session",
        "persist": False,
    },
    "max_iterations": 10,
}


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Initialised .harness workspace in tmp_path."""
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


@pytest.fixture()
def workspace_with_harness(workspace: Path) -> Path:
    """Workspace with a sample harness created."""
    hm.save_harness(
        name="my-harness",
        description="测试 Harness",
        skills=[],
        base=workspace,
    )
    return workspace


# ---------------------------------------------------------------------------
# Unit tests: agent module
# ---------------------------------------------------------------------------


class TestAgentValidation:
    def test_valid_agent(self) -> None:
        errors = am._validate_agent_data(SAMPLE_AGENT)
        assert errors == []

    def test_missing_name(self) -> None:
        data = {**SAMPLE_AGENT, "name": ""}
        errors = am._validate_agent_data(data)
        assert any("name" in e for e in errors)

    def test_missing_harness(self) -> None:
        data = {**SAMPLE_AGENT, "harness": ""}
        errors = am._validate_agent_data(data)
        assert any("harness" in e for e in errors)

    def test_invalid_memory_scope(self) -> None:
        data = {**SAMPLE_AGENT, "memory": {"scope": "invalid"}}
        errors = am._validate_agent_data(data)
        assert any("scope" in e for e in errors)

    def test_valid_memory_scopes(self) -> None:
        for scope in ("session", "harness", "global"):
            data = {**SAMPLE_AGENT, "memory": {"scope": scope}}
            errors = am._validate_agent_data(data)
            assert not any("scope" in e for e in errors)

    def test_invalid_max_iterations(self) -> None:
        data = {**SAMPLE_AGENT, "max_iterations": 0}
        errors = am._validate_agent_data(data)
        assert any("max_iterations" in e for e in errors)

    def test_non_integer_max_iterations(self) -> None:
        data = {**SAMPLE_AGENT, "max_iterations": "not-a-number"}
        errors = am._validate_agent_data(data)
        assert any("max_iterations" in e for e in errors)


class TestAgentCRUD:
    def test_save_and_load(self, workspace: Path) -> None:
        is_new = am.save_agent(
            name="test-agent",
            harness_ref="my-harness",
            base=workspace,
        )
        assert is_new is True
        data = am.load_agent("test-agent", base=workspace)
        assert data["name"] == "test-agent"
        assert data["harness"] == "my-harness"

    def test_overwrite_returns_false(self, workspace: Path) -> None:
        am.save_agent("agent-x", "h1", base=workspace)
        is_new = am.save_agent("agent-x", "h1-updated", base=workspace)
        assert is_new is False
        data = am.load_agent("agent-x", base=workspace)
        assert data["harness"] == "h1-updated"

    def test_file_stored_at_expected_path(self, workspace: Path) -> None:
        am.save_agent("my-agent", "some-harness", base=workspace)
        expected = workspace / ".harness" / "agents" / "my-agent.yaml"
        assert expected.exists()

    def test_load_nonexistent_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            am.load_agent("ghost", base=workspace)

    def test_delete(self, workspace: Path) -> None:
        am.save_agent("del-agent", "h", base=workspace)
        am.delete_agent("del-agent", base=workspace)
        with pytest.raises(FileNotFoundError):
            am.load_agent("del-agent", base=workspace)

    def test_delete_nonexistent_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            am.delete_agent("ghost", base=workspace)

    def test_list_agents_empty(self, workspace: Path) -> None:
        agents = am.list_agents(base=workspace)
        assert agents == []

    def test_list_agents(self, workspace: Path) -> None:
        am.save_agent("a1", "h1", base=workspace)
        am.save_agent("a2", "h2", base=workspace)
        agents = am.list_agents(base=workspace)
        names = [a["name"] for a in agents]
        assert "a1" in names
        assert "a2" in names

    def test_save_from_dict(self, workspace: Path) -> None:
        data = {
            "name": "dict-agent",
            "harness": "my-harness",
            "identity": {"name": "Dict Agent", "description": "from dict"},
            "memory": {"scope": "harness", "persist": True},
            "max_iterations": 5,
        }
        is_new = am.save_agent_from_dict(data, base=workspace)
        assert is_new is True
        loaded = am.load_agent("dict-agent", base=workspace)
        assert loaded["identity"]["name"] == "Dict Agent"
        assert loaded["memory"]["scope"] == "harness"
        assert loaded["max_iterations"] == 5

    def test_save_from_dict_no_name_raises(self, workspace: Path) -> None:
        with pytest.raises(ValueError):
            am.save_agent_from_dict({"harness": "h"}, base=workspace)

    def test_identity_defaults_to_name(self, workspace: Path) -> None:
        am.save_agent("my-agent", "h", base=workspace)
        data = am.load_agent("my-agent", base=workspace)
        assert data["identity"]["name"] == "my-agent"

    def test_all_fields_stored(self, workspace: Path) -> None:
        am.save_agent(
            name="full-agent",
            harness_ref="h@v0.1.0",
            identity_name="Full Agent",
            identity_description="desc",
            memory_scope="harness",
            memory_persist=True,
            max_iterations=20,
            base=workspace,
        )
        data = am.load_agent("full-agent", base=workspace)
        assert data["identity"]["name"] == "Full Agent"
        assert data["identity"]["description"] == "desc"
        assert data["memory"]["scope"] == "harness"
        assert data["memory"]["persist"] is True
        assert data["max_iterations"] == 20
        assert "created_at" in data


class TestAgentReferenceValidation:
    def test_valid_reference(self, workspace_with_harness: Path) -> None:
        am.save_agent("ag", "my-harness", base=workspace_with_harness)
        errors = am.validate_agent_references("ag", base=workspace_with_harness)
        assert errors == []

    def test_missing_harness(self, workspace: Path) -> None:
        am.save_agent("ag", "ghost-harness", base=workspace)
        errors = am.validate_agent_references("ag", base=workspace)
        assert any("ghost-harness" in e for e in errors)

    def test_nonexistent_agent(self, workspace: Path) -> None:
        errors = am.validate_agent_references("nonexistent", base=workspace)
        assert errors  # should have at least one error


class TestSaveConversation:
    def test_save_to_auto_path(self, workspace: Path) -> None:
        memory_data = {
            "turns": [
                {"role": "user", "content": "hello", "timestamp": "2026-01-01T00:00:00Z"},
                {"role": "assistant", "content": "hi", "timestamp": "2026-01-01T00:00:01Z"},
            ],
            "metadata": {"total_tokens": 10, "summary": None},
        }
        saved = am.save_conversation("my-agent", memory_data, base=workspace)
        assert saved.exists()
        loaded = json.loads(saved.read_text())
        assert loaded["agent"] == "my-agent"
        assert len(loaded["turns"]) == 2

    def test_save_to_custom_path(self, workspace: Path, tmp_path: Path) -> None:
        memory_data = {"turns": [], "metadata": {"total_tokens": 0, "summary": None}}
        target = tmp_path / "conv.json"
        saved = am.save_conversation("ag", memory_data, output_path=target, base=workspace)
        assert saved == target
        assert target.exists()


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestAgentCreateCLI:
    def test_create_basic(self, workspace_with_harness: Path) -> None:
        result = runner.invoke(app, ["agent", "create", "my-agent", "--harness", "my-harness"])
        assert result.exit_code == 0
        assert "Created" in result.output
        assert "my-agent" in result.output

    def test_create_with_options(self, workspace_with_harness: Path) -> None:
        result = runner.invoke(app, [
            "agent", "create", "fancy-agent",
            "--harness", "my-harness",
            "--identity-name", "Fancy Agent",
            "--description", "A fancy agent",
            "--memory-scope", "harness",
            "--persist",
            "--max-iterations", "5",
        ])
        assert result.exit_code == 0
        data = am.load_agent("fancy-agent", base=workspace_with_harness)
        assert data["identity"]["name"] == "Fancy Agent"
        assert data["memory"]["scope"] == "harness"
        assert data["max_iterations"] == 5

    def test_create_missing_harness_ref_fails(self, workspace: Path) -> None:
        result = runner.invoke(app, ["agent", "create", "my-agent", "--harness", "ghost-harness"])
        assert result.exit_code != 0
        assert "ghost-harness" in result.output.lower() or result.exit_code == 1

    def test_overwrite_shows_updated(self, workspace_with_harness: Path) -> None:
        runner.invoke(app, ["agent", "create", "same-agent", "--harness", "my-harness"])
        result = runner.invoke(app, ["agent", "create", "same-agent", "--harness", "my-harness"])
        assert result.exit_code == 0
        assert "Updated" in result.output


class TestAgentListCLI:
    def test_list_empty(self, workspace: Path) -> None:
        result = runner.invoke(app, ["agent", "list"])
        assert result.exit_code == 0
        assert "No agents found" in result.output

    def test_list_shows_agents(self, workspace_with_harness: Path) -> None:
        runner.invoke(app, ["agent", "create", "ag1", "--harness", "my-harness"])
        runner.invoke(app, ["agent", "create", "ag2", "--harness", "my-harness"])
        result = runner.invoke(app, ["agent", "list"])
        assert result.exit_code == 0
        assert "ag1" in result.output
        assert "ag2" in result.output


class TestAgentShowCLI:
    def test_show_agent(self, workspace_with_harness: Path) -> None:
        runner.invoke(app, [
            "agent", "create", "show-me",
            "--harness", "my-harness",
            "--description", "test desc",
        ])
        result = runner.invoke(app, ["agent", "show", "show-me"])
        assert result.exit_code == 0
        assert "show-me" in result.output
        assert "my-harness" in result.output

    def test_show_nonexistent(self, workspace: Path) -> None:
        result = runner.invoke(app, ["agent", "show", "ghost"])
        assert result.exit_code != 0


class TestAgentDeleteCLI:
    def test_delete_with_yes_flag(self, workspace_with_harness: Path) -> None:
        runner.invoke(app, ["agent", "create", "del-me", "--harness", "my-harness"])
        result = runner.invoke(app, ["agent", "delete", "del-me", "--yes"])
        assert result.exit_code == 0
        assert "Deleted" in result.output
        assert not am._agent_file("del-me", workspace_with_harness).exists()

    def test_delete_nonexistent(self, workspace: Path) -> None:
        result = runner.invoke(app, ["agent", "delete", "ghost", "--yes"])
        assert result.exit_code != 0


class TestAgentRunREPL:
    """Test the interactive REPL agent run command."""

    def _make_llm_response(self, content: str = "Assistant response"):
        from harness_kit.llm import LLMResponse
        return LLMResponse(
            content=content,
            model="gpt-4o",
            input_tokens=10,
            output_tokens=5,
            duration=0.1,
            finish_reason="stop",
        )

    def _patched_llm_config(self, content: str = "Assistant response"):
        """Return context managers that patch both LLMConfig and call_llm."""
        from harness_kit.llm import LLMConfig
        cfg = MagicMock(spec=LLMConfig)
        cfg.api_key = "test-key"
        cfg.model = "gpt-4o"
        return cfg

    def test_run_with_quit(self, workspace_with_harness: Path) -> None:
        runner.invoke(app, ["agent", "create", "chat-agent", "--harness", "my-harness"])
        mock_cfg = self._patched_llm_config()
        with patch("harness_kit.cli.LLMConfig") as MockLLMConfig, \
             patch("harness_kit.cli.call_llm") as mock_llm:
            MockLLMConfig.from_harness_config.return_value = mock_cfg
            mock_llm.return_value = self._make_llm_response()
            result = runner.invoke(app, ["agent", "run", "chat-agent"], input="/quit\n")
        assert result.exit_code == 0
        assert "Goodbye" in result.output

    def test_run_with_hello_then_quit(self, workspace_with_harness: Path) -> None:
        runner.invoke(app, ["agent", "create", "chat2", "--harness", "my-harness"])
        mock_cfg = self._patched_llm_config()
        with patch("harness_kit.cli.LLMConfig") as MockLLMConfig, \
             patch("harness_kit.cli.call_llm") as mock_llm:
            MockLLMConfig.from_harness_config.return_value = mock_cfg
            mock_llm.return_value = self._make_llm_response("Hello, I am here!")
            result = runner.invoke(
                app, ["agent", "run", "chat2"], input="hello\n/quit\n"
            )
        assert result.exit_code == 0
        assert "Hello, I am here!" in result.output

    def test_run_reset_clears_memory(self, workspace_with_harness: Path) -> None:
        runner.invoke(app, ["agent", "create", "mem-agent", "--harness", "my-harness"])
        mock_cfg = self._patched_llm_config()
        with patch("harness_kit.cli.LLMConfig") as MockLLMConfig, \
             patch("harness_kit.cli.call_llm") as mock_llm:
            MockLLMConfig.from_harness_config.return_value = mock_cfg
            mock_llm.return_value = self._make_llm_response()
            result = runner.invoke(
                app, ["agent", "run", "mem-agent"], input="hi\n/reset\n/quit\n"
            )
        assert result.exit_code == 0
        assert "Memory reset" in result.output

    def test_run_save_conversation(self, workspace_with_harness: Path, tmp_path: Path) -> None:
        runner.invoke(app, ["agent", "create", "save-agent", "--harness", "my-harness"])
        save_target = tmp_path / "conv.json"
        mock_cfg = self._patched_llm_config()
        with patch("harness_kit.cli.LLMConfig") as MockLLMConfig, \
             patch("harness_kit.cli.call_llm") as mock_llm:
            MockLLMConfig.from_harness_config.return_value = mock_cfg
            mock_llm.return_value = self._make_llm_response("test reply")
            result = runner.invoke(
                app, ["agent", "run", "save-agent"],
                input=f"hello\n/save {save_target}\n/quit\n",
            )
        assert result.exit_code == 0
        assert "saved" in result.output.lower()
        assert save_target.exists()

    def test_run_nonexistent_agent_fails(self, workspace: Path) -> None:
        result = runner.invoke(app, ["agent", "run", "ghost-agent"], input="/quit\n")
        assert result.exit_code != 0

    def test_run_no_api_key_fails(self, workspace_with_harness: Path) -> None:
        runner.invoke(app, ["agent", "create", "no-key-agent", "--harness", "my-harness"])
        mock_cfg = MagicMock()
        mock_cfg.api_key = None
        mock_cfg.model = "gpt-4o"
        with patch("harness_kit.cli.LLMConfig") as MockLLMConfig:
            MockLLMConfig.from_harness_config.return_value = mock_cfg
            result = runner.invoke(app, ["agent", "run", "no-key-agent"], input="/quit\n")
        # Should show API key error and exit non-zero
        assert result.exit_code != 0 or "API key" in result.output

    def test_run_memory_persisted_across_calls(self, workspace_with_harness: Path) -> None:
        """Memory with scope=harness should be persisted after each turn."""
        runner.invoke(app, [
            "agent", "create", "persist-agent",
            "--harness", "my-harness",
            "--memory-scope", "harness",
            "--persist",
        ])
        from harness_kit import memory as mm
        mock_cfg = self._patched_llm_config()

        with patch("harness_kit.cli.LLMConfig") as MockLLMConfig, \
             patch("harness_kit.cli.call_llm") as mock_llm:
            MockLLMConfig.from_harness_config.return_value = mock_cfg
            mock_llm.return_value = self._make_llm_response("turn 1 reply")
            runner.invoke(
                app, ["agent", "run", "persist-agent"], input="turn one\n/quit\n"
            )

        # Memory file should have been written
        mem_data = mm.load_memory("harness", "persist-agent", base=workspace_with_harness)
        assert len(mem_data["turns"]) > 0
        assert any(t["role"] == "user" and "turn one" in t["content"] for t in mem_data["turns"])
