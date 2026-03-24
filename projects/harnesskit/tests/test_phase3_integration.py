"""Phase 3.5 — End-to-end integration tests for the full Phase 3 workflow.

Covers:
  init → create prompt → create skill → create harness → create agent → run
  → memory persistence → error handling → performance
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit import agent as am
from harness_kit import harness as hm
from harness_kit import memory as mm
from harness_kit import prompt as pm
from harness_kit import rule as rm
from harness_kit import skill as sm

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def invoke(*args: str) -> tuple[int, str]:
    result = runner.invoke(app, list(args))
    return result.exit_code, result.output


def _make_llm_response(content: str = "Great code!"):
    """Build a minimal mocked LLMResponse."""
    from harness_kit.llm import LLMResponse
    return LLMResponse(
        content=content,
        model="gpt-4o",
        input_tokens=50,
        output_tokens=20,
        duration=0.2,
        finish_reason="stop",
    )


def _mock_openai_response(content: str = "OK") -> MagicMock:
    usage = MagicMock()
    usage.prompt_tokens = 50
    usage.completion_tokens = 20
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    resp.model = "gpt-4o"
    resp.id = "chatcmpl-test"
    return resp


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
def phase3_workspace(workspace: Path) -> Path:
    """Workspace with complete Phase 3 asset chain: prompt → skill → harness → agent."""
    # 1. Create a prompt (use short names to avoid rich table truncation)
    pm.save_prompt(
        name="sys-prompt",
        content="You are a helpful assistant. Language: {{language}}.",
        description="System prompt",
        tags=["assistant"],
        base=workspace,
    )
    pm.save_prompt(
        name="user-prompt",
        content="Please help with: {{task}}",
        description="User prompt",
        base=workspace,
    )

    # 2. Create a rule
    rm.save_rule(
        name="be-helpful",
        rule_type="soft",
        description="Always provide helpful and actionable responses",
        check_type="regex",
        pattern=r".",
        base=workspace,
    )

    # 3. Create a skill (short name to avoid rich truncation in 80-char terminal)
    sm.save_skill(
        name="help-skill",
        description="Assists with various tasks",
        trigger="When help is needed",
        inputs=[
            {"name": "task", "type": "string", "required": True},
            {"name": "language", "type": "string", "default": "English"},
        ],
        outputs=[{"name": "response", "type": "string"}],
        assets={
            "prompts": {
                "system": "sys-prompt",
                "user": "user-prompt",
            },
            "rules": ["be-helpful"],
        },
        changelog="Initial version",
        base=workspace,
    )

    # 4. Create a harness
    hm.save_harness(
        name="help-harness",
        description="Full assistant harness",
        skills=["help-skill"],
        model={"provider": "openai", "name": "gpt-4o", "temperature": 0.7, "max_tokens": 2000},
        memory={"scope": "harness", "max_turns": 5},
        base=workspace,
    )

    # 5. Create an agent
    am.save_agent(
        name="help-agent",
        harness_ref="help-harness",
        identity_name="助手",
        identity_description="帮助你完成各种任务",
        memory_scope="harness",
        memory_persist=True,
        max_iterations=10,
        base=workspace,
    )

    return workspace


# ---------------------------------------------------------------------------
# Test: Full Phase 3 end-to-end happy path
# ---------------------------------------------------------------------------


class TestFullPhase3Workflow:
    """Complete Phase 3 flow: init → prompt → skill → harness → agent → run."""

    def test_all_assets_exist_after_setup(self, phase3_workspace: Path) -> None:
        """All assets in the chain are accessible via CLI."""
        code, out = invoke("prompt", "list")
        assert code == 0
        assert "sys-prompt" in out

        code, out = invoke("skill", "list")
        assert code == 0
        assert "help-skill" in out

        code, out = invoke("harness", "list")
        assert code == 0
        assert "help-harness" in out

        code, out = invoke("agent", "list")
        assert code == 0
        assert "help-agent" in out

    def test_harness_validates_skill_references(self, phase3_workspace: Path) -> None:
        """Harness validates that referenced skills exist."""
        code, out = invoke("harness", "validate", "help-harness")
        assert code == 0
        assert "valid" in out.lower()

    def test_agent_references_harness(self, phase3_workspace: Path) -> None:
        """Agent references a valid harness."""
        errors = am.validate_agent_references("help-agent", base=phase3_workspace)
        assert errors == []

    def test_agent_show_contains_harness_ref(self, phase3_workspace: Path) -> None:
        code, out = invoke("agent", "show", "help-agent")
        assert code == 0
        assert "help-harness" in out
        assert "help-agent" in out

    def test_harness_show_contains_skills(self, phase3_workspace: Path) -> None:
        code, out = invoke("harness", "show", "help-harness")
        assert code == 0
        assert "help-skill" in out
        assert "gpt-4o" in out

    def test_doctor_passes_full_phase3_setup(self, phase3_workspace: Path) -> None:
        code, out = invoke("doctor")
        assert code == 0
        assert "Summary" in out

    def test_agent_run_quit(self, phase3_workspace: Path) -> None:
        """Agent REPL exits cleanly with /quit."""
        mock_cfg = MagicMock()
        mock_cfg.api_key = "sk-test"
        mock_cfg.model = "gpt-4o"
        with patch("harness_kit.cli.LLMConfig") as MockCfg, \
             patch("harness_kit.cli.call_llm") as mock_llm:
            MockCfg.from_harness_config.return_value = mock_cfg
            mock_llm.return_value = _make_llm_response()
            result = runner.invoke(app, ["agent", "run", "help-agent"], input="/quit\n")
        assert result.exit_code == 0
        assert "Goodbye" in result.output

    def test_agent_run_one_turn_then_quit(self, phase3_workspace: Path) -> None:
        """Agent REPL processes one message and returns LLM response."""
        mock_cfg = MagicMock()
        mock_cfg.api_key = "sk-test"
        mock_cfg.model = "gpt-4o"
        with patch("harness_kit.cli.LLMConfig") as MockCfg, \
             patch("harness_kit.cli.call_llm") as mock_llm:
            MockCfg.from_harness_config.return_value = mock_cfg
            mock_llm.return_value = _make_llm_response("Sure, I can help!")
            result = runner.invoke(
                app, ["agent", "run", "help-agent"],
                input="Help me with Python\n/quit\n",
            )
        assert result.exit_code == 0
        assert "Sure, I can help!" in result.output

    def test_agent_run_reset_clears_memory(self, phase3_workspace: Path) -> None:
        """Agent REPL /reset clears conversation history."""
        mock_cfg = MagicMock()
        mock_cfg.api_key = "sk-test"
        mock_cfg.model = "gpt-4o"
        with patch("harness_kit.cli.LLMConfig") as MockCfg, \
             patch("harness_kit.cli.call_llm") as mock_llm:
            MockCfg.from_harness_config.return_value = mock_cfg
            mock_llm.return_value = _make_llm_response()
            result = runner.invoke(
                app, ["agent", "run", "help-agent"],
                input="hi\n/reset\n/quit\n",
            )
        assert result.exit_code == 0
        assert "Memory reset" in result.output

    def test_agent_run_save_conversation(
        self, phase3_workspace: Path, tmp_path: Path
    ) -> None:
        """Agent REPL /save <path> saves conversation snapshot."""
        save_path = tmp_path / "session.json"
        mock_cfg = MagicMock()
        mock_cfg.api_key = "sk-test"
        mock_cfg.model = "gpt-4o"
        with patch("harness_kit.cli.LLMConfig") as MockCfg, \
             patch("harness_kit.cli.call_llm") as mock_llm:
            MockCfg.from_harness_config.return_value = mock_cfg
            mock_llm.return_value = _make_llm_response("saved response")
            result = runner.invoke(
                app, ["agent", "run", "help-agent"],
                input=f"hello\n/save {save_path}\n/quit\n",
            )
        assert result.exit_code == 0
        assert save_path.exists()
        data = json.loads(save_path.read_text())
        assert data["agent"] == "help-agent"
        assert len(data["turns"]) >= 2  # user + assistant

    def test_agent_memory_persisted_across_turns(self, phase3_workspace: Path) -> None:
        """Memory with scope=harness is persisted to disk after each turn."""
        mock_cfg = MagicMock()
        mock_cfg.api_key = "sk-test"
        mock_cfg.model = "gpt-4o"

        with patch("harness_kit.cli.LLMConfig") as MockCfg, \
             patch("harness_kit.cli.call_llm") as mock_llm:
            MockCfg.from_harness_config.return_value = mock_cfg
            mock_llm.return_value = _make_llm_response("remembered!")
            runner.invoke(
                app, ["agent", "run", "help-agent"],
                input="remember this: test_value\n/quit\n",
            )

        # Memory file should have been written to disk
        mem = mm.load_memory("harness", "help-agent", base=phase3_workspace)
        assert len(mem["turns"]) > 0
        user_turns = [t for t in mem["turns"] if t["role"] == "user"]
        assert any("test_value" in t["content"] for t in user_turns)


# ---------------------------------------------------------------------------
# Test: Memory system end-to-end
# ---------------------------------------------------------------------------


class TestMemorySystem:
    """Phase 3.3 memory: persistence, compression, search via CLI."""

    def test_memory_show_after_agent_run(self, phase3_workspace: Path) -> None:
        """memory show displays persisted conversation turns."""
        mock_cfg = MagicMock()
        mock_cfg.api_key = "sk-test"
        mock_cfg.model = "gpt-4o"

        with patch("harness_kit.cli.LLMConfig") as MockCfg, \
             patch("harness_kit.cli.call_llm") as mock_llm:
            MockCfg.from_harness_config.return_value = mock_cfg
            mock_llm.return_value = _make_llm_response("Hi there!")
            runner.invoke(
                app, ["agent", "run", "help-agent"],
                input="hello memory\n/quit\n",
            )

        code, out = invoke("memory", "show", "help-agent")
        assert code == 0
        assert "hello memory" in out

    def test_memory_search(self, phase3_workspace: Path) -> None:
        """memory search finds turns matching a keyword."""
        # Directly write memory for this test
        mem = mm.load_memory("harness", "search-test", base=phase3_workspace)
        mm.add_turn(mem, "user", "I love Python programming")
        mm.add_turn(mem, "assistant", "Python is great!")
        mm.add_turn(mem, "user", "Tell me about JavaScript")
        mm.save_memory(mem, "harness", "search-test", base=phase3_workspace)

        code, out = invoke("memory", "search", "search-test", "Python")
        assert code == 0
        assert "Python" in out

    def test_memory_clear(self, phase3_workspace: Path) -> None:
        """memory clear removes persisted memory for a harness."""
        mem = mm.load_memory("harness", "help-agent", base=phase3_workspace)
        mm.add_turn(mem, "user", "test message")
        mm.save_memory(mem, "harness", "help-agent", base=phase3_workspace)

        code, out = invoke("memory", "clear", "help-agent", "--yes")
        assert code == 0
        assert "cleared" in out.lower() or "Cleared" in out

        # Memory file should be gone (create_memory returns empty state)
        fresh = mm.load_memory("harness", "help-agent", base=phase3_workspace)
        assert fresh["turns"] == []

    def test_memory_list(self, phase3_workspace: Path) -> None:
        """memory list shows all persisted memory files."""
        mem = mm._empty_memory()
        mm.save_memory(mem, "harness", "help-agent", base=phase3_workspace)

        code, out = invoke("memory", "list")
        assert code == 0
        assert "help-agent" in out

    def test_memory_compression_on_overflow(self, phase3_workspace: Path) -> None:
        """Memory auto-compresses when max_turns is exceeded."""
        harness_data = hm.load_harness("help-harness", base=phase3_workspace)
        max_turns = harness_data["memory"]["max_turns"]  # 5

        # Add more turns than the limit
        mem = mm._empty_memory()
        for i in range(max_turns + 3):
            mm.add_turn(mem, "user", f"User message {i}")
            mm.add_turn(mem, "assistant", f"Assistant reply {i}")

        # Compress without LLM (fallback plain-text summary)
        mm.compress_memory(mem, max_turns=max_turns, llm_config=None)

        # After compression, turns should be <= max_turns
        assert len(mem["turns"]) <= max_turns


# ---------------------------------------------------------------------------
# Test: Harness multi-skill composition
# ---------------------------------------------------------------------------


class TestHarnessComposition:
    """Test that harness correctly references and loads multiple skills."""

    def test_harness_with_multiple_skills(self, workspace: Path) -> None:
        sm.save_skill("skill-a", description="Skill A", base=workspace)
        sm.save_skill("skill-b", description="Skill B", base=workspace)
        sm.save_skill("skill-c", description="Skill C", base=workspace)

        hm.save_harness(
            "multi-skill",
            description="Multi-skill harness",
            skills=["skill-a", "skill-b", "skill-c"],
            base=workspace,
        )

        data = hm.load_harness("multi-skill", base=workspace)
        assert len(data["skills"]) == 3
        assert "skill-a" in data["skills"]
        assert "skill-b" in data["skills"]
        assert "skill-c" in data["skills"]

    def test_harness_clone_preserves_skills(self, workspace: Path) -> None:
        sm.save_skill("skill-x", description="X", base=workspace)
        hm.save_harness(
            "original-h",
            description="Original",
            skills=["skill-x"],
            base=workspace,
        )
        hm.clone_harness("original-h", "cloned-h", workspace)

        cloned = hm.load_harness("cloned-h", base=workspace)
        assert "skill-x" in cloned["skills"]
        assert cloned["version"] == "v0.0.1"

    def test_harness_diff_shows_changes(self, workspace: Path) -> None:
        hm.save_harness("diff-h", description="first", skills=["s1"], base=workspace)
        hm.save_harness("diff-h", description="second", skills=["s1", "s2"], base=workspace)

        code, out = invoke("harness", "diff", "diff-h@v0.0.1", "diff-h@v0.0.2")
        assert code == 0
        assert "s2" in out or "second" in out

    def test_harness_version_history(self, workspace: Path) -> None:
        for i in range(3):
            hm.save_harness("versioned-h", description=f"version {i}", base=workspace)

        versions = hm.list_versions("versioned-h", workspace)
        assert len(versions) == 3
        assert "v0.0.1" in versions
        assert "v0.0.3" in versions


# ---------------------------------------------------------------------------
# Test: Error handling (Phase 3.5 requirement)
# ---------------------------------------------------------------------------


class TestPhase3ErrorHandling:
    """All errors should have clear messages and fix suggestions."""

    def test_harness_create_without_init(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        code, out = invoke("harness", "create", "h1", "--description", "test")
        assert code != 0
        assert "init" in out.lower()

    def test_agent_create_without_init(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        code, out = invoke("agent", "create", "a1", "--harness", "h1")
        assert code != 0
        assert "init" in out.lower()

    def test_agent_create_missing_harness_fails(self, workspace: Path) -> None:
        code, out = invoke("agent", "create", "ag", "--harness", "ghost-harness")
        assert code != 0
        assert "ghost-harness" in out.lower() or code == 1

    def test_harness_show_not_found(self, workspace: Path) -> None:
        code, out = invoke("harness", "show", "nonexistent")
        assert code != 0
        assert "not found" in out.lower() or "nonexistent" in out

    def test_agent_show_not_found(self, workspace: Path) -> None:
        code, out = invoke("agent", "show", "nonexistent")
        assert code != 0

    def test_agent_run_not_found(self, workspace: Path) -> None:
        result = runner.invoke(app, ["agent", "run", "ghost"], input="/quit\n")
        assert result.exit_code != 0

    def test_agent_run_no_api_key_error(self, workspace: Path) -> None:
        """Running agent without API key gives clear error."""
        hm.save_harness("h1", description="test", base=workspace)
        am.save_agent("ag", "h1", base=workspace)

        mock_cfg = MagicMock()
        mock_cfg.api_key = None
        mock_cfg.model = "gpt-4o"

        with patch("harness_kit.cli.LLMConfig") as MockCfg:
            MockCfg.from_harness_config.return_value = mock_cfg
            result = runner.invoke(app, ["agent", "run", "ag"], input="/quit\n")

        assert result.exit_code != 0 or "api" in result.output.lower() or "key" in result.output.lower()

    def test_harness_validate_broken_skill_ref(self, workspace: Path) -> None:
        """Harness with broken skill reference fails validation."""
        hm.save_harness(
            "broken-h",
            description="Broken",
            skills=["ghost-skill@v0.1.0"],
            base=workspace,
        )
        code, out = invoke("harness", "validate", "broken-h")
        assert code != 0
        assert "ghost-skill" in out

    def test_harness_delete_nonexistent(self, workspace: Path) -> None:
        code, out = invoke("harness", "delete", "ghost", "--yes")
        assert code != 0
        assert "not found" in out.lower()

    def test_agent_delete_nonexistent(self, workspace: Path) -> None:
        code, out = invoke("agent", "delete", "ghost", "--yes")
        assert code != 0

    def test_harness_clone_to_existing_fails(self, workspace: Path) -> None:
        hm.save_harness("h1", description="first", base=workspace)
        hm.save_harness("h2", description="second", base=workspace)
        code, out = invoke("harness", "clone", "h1", "h2")
        assert code != 0
        assert "exists" in out.lower() or "already" in out.lower()

    def test_memory_show_not_found(self, workspace: Path) -> None:
        """memory show for non-existent harness should handle gracefully."""
        code, out = invoke("memory", "show", "nonexistent")
        # Should either show empty memory or return error — not crash
        assert code == 0 or "not found" in out.lower() or "empty" in out.lower() or "No turns" in out

    def test_memory_clear_with_yes_flag(self, workspace: Path) -> None:
        """memory clear --yes should not prompt and should succeed."""
        code, out = invoke("memory", "clear", "some-harness", "--yes")
        # Either clears (success) or gracefully reports nothing to clear
        assert code == 0 or "not found" in out.lower() or "nothing" in out.lower()


# ---------------------------------------------------------------------------
# Test: Full init-to-run end-to-end via CLI only
# ---------------------------------------------------------------------------


class TestFullCLIWorkflow:
    """End-to-end test using only CLI commands (no direct module access)."""

    def test_complete_phase3_workflow_via_cli(
        self, workspace: Path
    ) -> None:
        """Acceptance criterion: init → prompt → skill → harness → agent → validate chain."""
        # 1. Verify init worked
        code, out = invoke("doctor")
        assert code == 0

        # 2. Create prompt via CLI
        code, out = invoke(
            "prompt", "save", "sys-prompt",
            "--content", "You are a helpful AI.",
            "--description", "System prompt",
        )
        assert code == 0, f"prompt save failed: {out}"

        # 3. Create skill via CLI
        skill_yaml = workspace / "test-skill.yaml"
        skill_yaml.write_text(yaml.dump({
            "name": "test-skill",
            "description": "A test skill",
            "trigger": "test",
            "inputs": [{"name": "q", "type": "string", "required": True}],
            "outputs": [{"name": "a", "type": "string"}],
            "assets": {"prompts": {"system": "sys-prompt"}},
            "changelog": "initial",
        }, allow_unicode=True))
        code, out = invoke("skill", "save", "--file", str(skill_yaml))
        assert code == 0, f"skill save failed: {out}"

        # 4. Create harness via CLI
        code, out = invoke(
            "harness", "create", "test-harness",
            "--description", "Test harness",
            "--skills", "test-skill",
        )
        assert code == 0, f"harness create failed: {out}"
        assert "test-harness" in out
        assert "v0.0.1" in out

        # 5. Create agent via CLI
        code, out = invoke(
            "agent", "create", "test-agent",
            "--harness", "test-harness",
            "--identity-name", "Test Agent",
            "--description", "A test agent",
        )
        assert code == 0, f"agent create failed: {out}"
        assert "test-agent" in out

        # 6. Show agent and verify references
        code, out = invoke("agent", "show", "test-agent")
        assert code == 0
        assert "test-harness" in out

        # 7. Validate harness references
        # Note: skill reference is by name (no version), so it will find it
        code, out = invoke("harness", "validate", "test-harness")
        assert code == 0, f"harness validate failed: {out}"

        # 8. Verify doctor still passes
        code, out = invoke("doctor")
        assert code == 0

    def test_agent_list_shows_all_created(self, workspace: Path) -> None:
        for i in range(3):
            hm.save_harness(f"h{i}", description=f"Harness {i}", base=workspace)
            am.save_agent(f"agent-{i}", f"h{i}", base=workspace)

        code, out = invoke("agent", "list")
        assert code == 0
        for i in range(3):
            assert f"agent-{i}" in out

    def test_harness_list_shows_all_created(self, workspace: Path) -> None:
        for name in ["alpha", "beta", "gamma"]:
            hm.save_harness(name, description=f"{name} harness", base=workspace)

        code, out = invoke("harness", "list")
        assert code == 0
        assert "alpha" in out
        assert "beta" in out
        assert "gamma" in out


# ---------------------------------------------------------------------------
# Test: Performance baselines (Phase 3 operations)
# ---------------------------------------------------------------------------


class TestPhase3Performance:
    """Lightweight performance baselines for Phase 3 local operations."""

    def test_save_50_harness_versions_under_2s(self, workspace: Path) -> None:
        """Saving 50 harness versions should complete in under 2 seconds."""
        start = time.monotonic()
        for i in range(50):
            hm.save_harness(
                "perf-harness",
                description=f"Performance version {i}",
                skills=[],
                base=workspace,
            )
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"50 harness saves took {elapsed:.2f}s (expected < 2s)"
        assert len(hm.list_versions("perf-harness", workspace)) == 50

    def test_save_100_agents_under_2s(self, workspace: Path) -> None:
        """Creating 100 agents should complete in under 2 seconds."""
        # Create a harness first
        hm.save_harness("h", description="base", base=workspace)
        start = time.monotonic()
        for i in range(100):
            am.save_agent(f"agent-{i}", "h", base=workspace)
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"100 agent saves took {elapsed:.2f}s (expected < 2s)"
        assert len(am.list_agents(base=workspace)) == 100

    def test_load_harness_50x_under_500ms(self, workspace: Path) -> None:
        """Loading the current harness version 50 times should be under 500ms."""
        hm.save_harness("fast-h", description="fast", base=workspace)
        start = time.monotonic()
        for _ in range(50):
            hm.load_harness("fast-h", base=workspace)
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"50 harness loads took {elapsed:.3f}s (expected < 0.5s)"

    def test_memory_add_100_turns_under_500ms(self, workspace: Path) -> None:
        """Adding 100 turns to memory and saving should be under 500ms."""
        mem = mm._empty_memory()
        start = time.monotonic()
        for i in range(100):
            mm.add_turn(mem, "user", f"Message {i}")
            mm.add_turn(mem, "assistant", f"Reply {i}")
        mm.save_memory(mem, "harness", "perf-test", base=workspace)
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"100 turn memory ops took {elapsed:.3f}s (expected < 0.5s)"
        assert len(mem["turns"]) == 200

    def test_memory_compress_under_100ms(self, workspace: Path) -> None:
        """Compressing memory with 20 turns should be under 100ms."""
        mem = mm._empty_memory()
        for i in range(20):
            mm.add_turn(mem, "user", f"Long user message number {i} with some content")
            mm.add_turn(mem, "assistant", f"Detailed assistant reply number {i}")
        start = time.monotonic()
        mm.compress_memory(mem, max_turns=5, llm_config=None)
        elapsed = time.monotonic() - start
        assert elapsed < 0.1, f"Memory compression took {elapsed:.3f}s (expected < 0.1s)"
        assert len(mem["turns"]) <= 5
