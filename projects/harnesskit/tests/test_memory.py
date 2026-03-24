"""Tests for Phase 3.3: Memory 记忆系统."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from harness_kit import memory as mm
from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit import harness as hm
from harness_kit import skill as sm

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
def workspace_with_harness(workspace: Path) -> tuple[Path, str]:
    sm.save_skill("mem-skill", description="Memory test skill", base=workspace)
    hm.save_harness(
        "mem-harness",
        description="Memory harness",
        skills=["mem-skill"],
        memory={"scope": "harness", "max_turns": 4},
        base=workspace,
    )
    return workspace, "mem-harness"


# ---------------------------------------------------------------------------
# Unit tests: empty_memory
# ---------------------------------------------------------------------------


class TestEmptyMemory:
    def test_has_turns_and_metadata(self) -> None:
        data = mm.load_memory("session", "any-harness")
        assert "turns" in data
        assert "metadata" in data
        assert data["turns"] == []
        assert data["metadata"]["total_tokens"] == 0
        assert data["metadata"]["summary"] is None


# ---------------------------------------------------------------------------
# Unit tests: add_turn
# ---------------------------------------------------------------------------


class TestAddTurn:
    def test_adds_user_turn(self) -> None:
        mem = mm.load_memory("session", "h")
        mm.add_turn(mem, "user", "hello")
        assert len(mem["turns"]) == 1
        assert mem["turns"][0]["role"] == "user"
        assert mem["turns"][0]["content"] == "hello"

    def test_adds_assistant_turn(self) -> None:
        mem = mm.load_memory("session", "h")
        mm.add_turn(mem, "assistant", "world", tokens=15)
        assert mem["turns"][0]["role"] == "assistant"
        assert mem["metadata"]["total_tokens"] == 15

    def test_token_accumulation(self) -> None:
        mem = mm.load_memory("session", "h")
        mm.add_turn(mem, "user", "q1", tokens=10)
        mm.add_turn(mem, "assistant", "a1", tokens=20)
        assert mem["metadata"]["total_tokens"] == 30

    def test_timestamp_present(self) -> None:
        mem = mm.load_memory("session", "h")
        mm.add_turn(mem, "user", "hi")
        assert "timestamp" in mem["turns"][0]


# ---------------------------------------------------------------------------
# Unit tests: get_history_messages
# ---------------------------------------------------------------------------


class TestGetHistoryMessages:
    def test_returns_role_content_pairs(self) -> None:
        mem = mm.load_memory("session", "h")
        mm.add_turn(mem, "user", "question")
        mm.add_turn(mem, "assistant", "answer")
        msgs = mm.get_history_messages(mem)
        assert msgs == [
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ]

    def test_empty_memory_returns_empty_list(self) -> None:
        mem = mm.load_memory("session", "h")
        assert mm.get_history_messages(mem) == []


# ---------------------------------------------------------------------------
# Unit tests: search_memory
# ---------------------------------------------------------------------------


class TestSearchMemory:
    def test_finds_matching_turn(self) -> None:
        mem = mm.load_memory("session", "h")
        mm.add_turn(mem, "user", "Python is great")
        mm.add_turn(mem, "assistant", "I agree")
        results = mm.search_memory(mem, "python")
        assert len(results) == 1
        assert results[0]["content"] == "Python is great"

    def test_case_insensitive(self) -> None:
        mem = mm.load_memory("session", "h")
        mm.add_turn(mem, "user", "HELLO WORLD")
        results = mm.search_memory(mem, "hello")
        assert len(results) == 1

    def test_no_match_returns_empty(self) -> None:
        mem = mm.load_memory("session", "h")
        mm.add_turn(mem, "user", "nothing relevant")
        assert mm.search_memory(mem, "xyz123") == []

    def test_empty_memory_returns_empty(self) -> None:
        mem = mm.load_memory("session", "h")
        assert mm.search_memory(mem, "anything") == []


# ---------------------------------------------------------------------------
# Unit tests: compress_memory
# ---------------------------------------------------------------------------


class TestCompressMemory:
    def test_no_compress_when_under_limit(self) -> None:
        mem = mm.load_memory("session", "h")
        for i in range(3):
            mm.add_turn(mem, "user", f"msg {i}")
        result = mm.compress_memory(mem, max_turns=4)
        assert result is False
        assert len(mem["turns"]) == 3

    def test_compresses_when_over_limit(self) -> None:
        mem = mm.load_memory("session", "h")
        for i in range(6):
            mm.add_turn(mem, "user", f"msg {i}")
        result = mm.compress_memory(mem, max_turns=4)
        assert result is True
        # Should keep last max_turns//2 = 2 turns
        assert len(mem["turns"]) == 2

    def test_summary_is_set_after_compression(self) -> None:
        mem = mm.load_memory("session", "h")
        for i in range(6):
            mm.add_turn(mem, "user", f"turn {i}")
        mm.compress_memory(mem, max_turns=4)
        assert mem["metadata"]["summary"] is not None
        assert len(mem["metadata"]["summary"]) > 0

    def test_recent_turns_kept(self) -> None:
        mem = mm.load_memory("session", "h")
        for i in range(6):
            mm.add_turn(mem, "user", f"msg-{i}")
        mm.compress_memory(mem, max_turns=4)
        # Only last 2 should be kept (max_turns//2 = 2)
        contents = [t["content"] for t in mem["turns"]]
        assert "msg-4" in contents
        assert "msg-5" in contents
        assert "msg-0" not in contents


# ---------------------------------------------------------------------------
# Unit tests: save / load persistence
# ---------------------------------------------------------------------------


class TestMemoryPersistence:
    def test_session_scope_not_persisted(self, workspace: Path) -> None:
        """Session scope never writes to disk."""
        mem = mm.load_memory("session", "test-h")
        mm.add_turn(mem, "user", "session message")
        mm.save_memory(mem, "session", "test-h", base=workspace)
        mem_file = workspace / ".harness" / "memory" / "test-h.json"
        assert not mem_file.exists()

    def test_harness_scope_persisted(self, workspace: Path) -> None:
        """Harness scope writes to .harness/memory/{name}.json."""
        mem = mm.load_memory("harness", "test-h", base=workspace)
        mm.add_turn(mem, "user", "persisted message")
        mm.save_memory(mem, "harness", "test-h", base=workspace)
        mem_file = workspace / ".harness" / "memory" / "test-h.json"
        assert mem_file.exists()
        data = json.loads(mem_file.read_text())
        assert len(data["turns"]) == 1
        assert data["turns"][0]["content"] == "persisted message"

    def test_global_scope_uses_global_file(self, workspace: Path) -> None:
        """Global scope writes to .harness/memory/global.json."""
        mem = mm.load_memory("global", "any-h", base=workspace)
        mm.add_turn(mem, "user", "global message")
        mm.save_memory(mem, "global", "any-h", base=workspace)
        global_file = workspace / ".harness" / "memory" / "global.json"
        assert global_file.exists()
        data = json.loads(global_file.read_text())
        assert data["turns"][0]["content"] == "global message"

    def test_load_returns_saved_data(self, workspace: Path) -> None:
        """load_memory returns previously saved turns."""
        mem = mm.load_memory("harness", "reload-h", base=workspace)
        mm.add_turn(mem, "user", "turn1")
        mm.add_turn(mem, "assistant", "reply1")
        mm.save_memory(mem, "harness", "reload-h", base=workspace)

        mem2 = mm.load_memory("harness", "reload-h", base=workspace)
        assert len(mem2["turns"]) == 2
        assert mem2["turns"][0]["content"] == "turn1"
        assert mem2["turns"][1]["content"] == "reply1"

    def test_load_missing_returns_empty(self, workspace: Path) -> None:
        data = mm.load_memory("harness", "nonexistent", base=workspace)
        assert data["turns"] == []

    def test_clear_removes_file(self, workspace: Path) -> None:
        mem = mm.load_memory("harness", "clear-h", base=workspace)
        mm.add_turn(mem, "user", "to be cleared")
        mm.save_memory(mem, "harness", "clear-h", base=workspace)
        assert mm.clear_memory("harness", "clear-h", base=workspace) is True
        assert not (workspace / ".harness" / "memory" / "clear-h.json").exists()

    def test_clear_session_returns_false(self, workspace: Path) -> None:
        assert mm.clear_memory("session", "any", base=workspace) is False

    def test_clear_missing_returns_false(self, workspace: Path) -> None:
        assert mm.clear_memory("harness", "not-there", base=workspace) is False


# ---------------------------------------------------------------------------
# Unit tests: list_memory_files
# ---------------------------------------------------------------------------


class TestListMemoryFiles:
    def test_empty_when_no_files(self, workspace: Path) -> None:
        assert mm.list_memory_files(base=workspace) == []

    def test_lists_existing_files(self, workspace: Path) -> None:
        for name in ["alpha", "beta"]:
            mem = mm.load_memory("harness", name, base=workspace)
            mm.add_turn(mem, "user", f"hello from {name}")
            mm.save_memory(mem, "harness", name, base=workspace)
        files = mm.list_memory_files(base=workspace)
        names = [f["harness"] for f in files]
        assert "alpha" in names
        assert "beta" in names

    def test_global_scope_detected(self, workspace: Path) -> None:
        mem = mm.load_memory("global", "any", base=workspace)
        mm.add_turn(mem, "user", "g msg")
        mm.save_memory(mem, "global", "any", base=workspace)
        files = mm.list_memory_files(base=workspace)
        global_entry = next((f for f in files if f["harness"] == "global"), None)
        assert global_entry is not None
        assert global_entry["scope"] == "global"


# ---------------------------------------------------------------------------
# CLI integration: memory commands
# ---------------------------------------------------------------------------


class TestMemoryCLIShow:
    def test_show_empty(self, workspace: Path) -> None:
        result = runner.invoke(app, ["memory", "show", "no-harness"])
        assert result.exit_code == 0
        assert "No memory" in result.output or "no memory" in result.output.lower()

    def test_show_with_turns(self, workspace: Path) -> None:
        mem = mm.load_memory("harness", "show-h")
        mm.add_turn(mem, "user", "test question")
        mm.add_turn(mem, "assistant", "test answer")
        mm.save_memory(mem, "harness", "show-h")
        result = runner.invoke(app, ["memory", "show", "show-h"])
        assert result.exit_code == 0
        assert "test question" in result.output
        assert "test answer" in result.output

    def test_show_with_summary(self, workspace: Path) -> None:
        mem = mm.load_memory("harness", "sum-h")
        mem["metadata"]["summary"] = "This is a compressed summary"
        mm.save_memory(mem, "harness", "sum-h")
        result = runner.invoke(app, ["memory", "show", "sum-h"])
        assert result.exit_code == 0
        assert "summary" in result.output.lower() or "Summary" in result.output


class TestMemoryCLIList:
    def test_list_empty(self, workspace: Path) -> None:
        result = runner.invoke(app, ["memory", "list"])
        assert result.exit_code == 0
        assert "No memory" in result.output or "no memory" in result.output.lower()

    def test_list_shows_files(self, workspace: Path) -> None:
        mem = mm.load_memory("harness", "listed-h")
        mm.add_turn(mem, "user", "hi")
        mm.save_memory(mem, "harness", "listed-h")
        result = runner.invoke(app, ["memory", "list"])
        assert result.exit_code == 0
        assert "listed-h" in result.output


class TestMemoryCLISearch:
    def test_search_finds_match(self, workspace: Path) -> None:
        mem = mm.load_memory("harness", "search-h")
        mm.add_turn(mem, "user", "Python best practices")
        mm.save_memory(mem, "harness", "search-h")
        result = runner.invoke(app, ["memory", "search", "search-h", "python"])
        assert result.exit_code == 0
        assert "Python best practices" in result.output

    def test_search_no_match(self, workspace: Path) -> None:
        mem = mm.load_memory("harness", "search-empty-h")
        mm.add_turn(mem, "user", "something else")
        mm.save_memory(mem, "harness", "search-empty-h")
        result = runner.invoke(app, ["memory", "search", "search-empty-h", "xyzabc"])
        assert result.exit_code == 0
        assert "No turns" in result.output or "no turns" in result.output.lower()


class TestMemoryCLIClear:
    def test_clear_with_yes_flag(self, workspace: Path) -> None:
        mem = mm.load_memory("harness", "clear-cli-h")
        mm.add_turn(mem, "user", "to delete")
        mm.save_memory(mem, "harness", "clear-cli-h")
        result = runner.invoke(app, ["memory", "clear", "clear-cli-h", "--yes"])
        assert result.exit_code == 0
        assert "cleared" in result.output.lower() or "Memory cleared" in result.output
        # File should be gone
        assert not (workspace / ".harness" / "memory" / "clear-cli-h.json").exists()

    def test_clear_nonexistent_is_graceful(self, workspace: Path) -> None:
        result = runner.invoke(app, ["memory", "clear", "nonexistent", "--yes"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Integration: harness run with memory
# ---------------------------------------------------------------------------


class TestHarnessRunMemoryIntegration:
    def _make_mock_response(self, content: str = "Mock output") -> MagicMock:
        resp = MagicMock()
        resp.content = content
        resp.model = "gpt-4o"
        resp.input_tokens = 30
        resp.output_tokens = 15
        resp.duration = 0.3
        return resp

    def test_harness_run_saves_memory(
        self, workspace_with_harness: tuple[Path, str]
    ) -> None:
        """After a successful harness run, memory file should be created."""
        workspace, harness_name = workspace_with_harness
        mock_resp = self._make_mock_response("Great answer")

        with patch("harness_kit.llm.call_llm", return_value=mock_resp), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = runner.invoke(
                app,
                ["harness", "run", harness_name, "--var", "query=hello"],
            )

        assert result.exit_code == 0, result.output
        mem_file = workspace / ".harness" / "memory" / f"{harness_name}.json"
        assert mem_file.exists()
        data = json.loads(mem_file.read_text())
        assert len(data["turns"]) == 2
        # user turn has the input
        assert "query=hello" in data["turns"][0]["content"]
        # assistant turn has the output
        assert "Great answer" in data["turns"][1]["content"]

    def test_harness_run_no_memory_flag(
        self, workspace_with_harness: tuple[Path, str]
    ) -> None:
        """--no-memory prevents file creation."""
        workspace, harness_name = workspace_with_harness
        mock_resp = self._make_mock_response()

        with patch("harness_kit.llm.call_llm", return_value=mock_resp), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = runner.invoke(
                app,
                ["harness", "run", harness_name, "--no-memory"],
            )

        assert result.exit_code == 0, result.output
        mem_file = workspace / ".harness" / "memory" / f"{harness_name}.json"
        assert not mem_file.exists()

    def test_harness_run_loads_previous_memory(
        self, workspace_with_harness: tuple[Path, str]
    ) -> None:
        """Second run shows memory loaded indicator."""
        workspace, harness_name = workspace_with_harness
        # Pre-populate memory
        mem = mm.load_memory("harness", harness_name)
        mm.add_turn(mem, "user", "previous question")
        mm.add_turn(mem, "assistant", "previous answer")
        mm.save_memory(mem, "harness", harness_name)

        mock_resp = self._make_mock_response()
        with patch("harness_kit.llm.call_llm", return_value=mock_resp), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = runner.invoke(
                app,
                ["harness", "run", harness_name],
            )

        assert result.exit_code == 0, result.output
        assert "turn" in result.output.lower() or "loaded" in result.output.lower()

    def test_harness_run_accumulates_turns(
        self, workspace_with_harness: tuple[Path, str]
    ) -> None:
        """Running twice accumulates 4 turns (2 per run)."""
        workspace, harness_name = workspace_with_harness
        mock_resp = self._make_mock_response()

        with patch("harness_kit.llm.call_llm", return_value=mock_resp), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            runner.invoke(app, ["harness", "run", harness_name, "--var", "q=first"])
            runner.invoke(app, ["harness", "run", harness_name, "--var", "q=second"])

        mem_file = workspace / ".harness" / "memory" / f"{harness_name}.json"
        data = json.loads(mem_file.read_text())
        assert len(data["turns"]) == 4

    def test_harness_run_compresses_when_over_max_turns(
        self, workspace_with_harness: tuple[Path, str]
    ) -> None:
        """After exceeding max_turns, compression runs and summary is set."""
        workspace, harness_name = workspace_with_harness
        mock_resp = self._make_mock_response()

        # Run 3 times: each run adds 2 turns → 6 turns, max_turns=4 triggers compression
        with patch("harness_kit.llm.call_llm", return_value=mock_resp), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            for i in range(3):
                runner.invoke(app, ["harness", "run", harness_name, "--var", f"q=run{i}"])

        mem_file = workspace / ".harness" / "memory" / f"{harness_name}.json"
        data = json.loads(mem_file.read_text())
        # Turns should be ≤ max_turns (4) after compression
        assert len(data["turns"]) <= 4
        assert data["metadata"]["summary"] is not None
