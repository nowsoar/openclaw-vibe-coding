"""Tests for Phase 1.2: prompt asset management."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit import prompt as pm

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


# ---------------------------------------------------------------------------
# Unit tests — prompt module
# ---------------------------------------------------------------------------


class TestVersionHelpers:
    def test_parse_version(self) -> None:
        from harness_kit.prompt import _parse_version
        assert _parse_version("v1.2.3") == (1, 2, 3)
        assert _parse_version("v0.0.1") == (0, 0, 1)

    def test_bump_patch(self) -> None:
        from harness_kit.prompt import _bump_patch
        assert _bump_patch("v0.0.1") == "v0.0.2"
        assert _bump_patch("v1.2.9") == "v1.2.10"


class TestSavePrompt:
    def test_first_save_creates_v001(self, workspace: Path) -> None:
        ver, is_new = pm.save_prompt("hello", "content here", base=workspace)
        assert ver == "v0.0.1"
        assert is_new is True

    def test_second_save_bumps_patch(self, workspace: Path) -> None:
        pm.save_prompt("hello", "v1", base=workspace)
        ver, is_new = pm.save_prompt("hello", "v2", base=workspace)
        assert ver == "v0.0.2"
        assert is_new is False

    def test_current_file_updated(self, workspace: Path) -> None:
        pm.save_prompt("hello", "v1", base=workspace)
        pm.save_prompt("hello", "v2", base=workspace)
        assert pm.get_current_version("hello", workspace) == "v0.0.2"

    def test_yaml_file_created(self, workspace: Path) -> None:
        pm.save_prompt("myprompt", "some content", description="desc", base=workspace)
        vf = workspace / ".harness" / "prompts" / "myprompt" / "v0.0.1.yaml"
        assert vf.exists()
        data = yaml.safe_load(vf.read_text())
        assert data["content"] == "some content"
        assert data["description"] == "desc"
        assert data["version"] == "v0.0.1"
        assert data["name"] == "myprompt"

    def test_multiline_content_preserved(self, workspace: Path) -> None:
        content = "line one\nline two\n  indented\n"
        pm.save_prompt("multi", content, base=workspace)
        data = pm.load_prompt("multi", base=workspace)
        assert data["content"] == content

    def test_tags_stored(self, workspace: Path) -> None:
        pm.save_prompt("tagged", "c", tags=["a", "b"], base=workspace)
        data = pm.load_prompt("tagged", base=workspace)
        assert data["tags"] == ["a", "b"]

    def test_variables_stored(self, workspace: Path) -> None:
        variables = [{"name": "lang", "required": True}]
        pm.save_prompt("withvars", "{{lang}}", variables=variables, base=workspace)
        data = pm.load_prompt("withvars", base=workspace)
        assert data["variables"] == variables


class TestLoadPrompt:
    def test_load_current(self, workspace: Path) -> None:
        pm.save_prompt("p", "hello", base=workspace)
        data = pm.load_prompt("p", base=workspace)
        assert data["content"] == "hello"

    def test_load_specific_version(self, workspace: Path) -> None:
        pm.save_prompt("p", "first", base=workspace)
        pm.save_prompt("p", "second", base=workspace)
        data = pm.load_prompt("p", "v0.0.1", workspace)
        assert data["content"] == "first"

    def test_load_missing_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            pm.load_prompt("missing", base=workspace)

    def test_load_missing_version_raises(self, workspace: Path) -> None:
        pm.save_prompt("p", "x", base=workspace)
        with pytest.raises(FileNotFoundError):
            pm.load_prompt("p", "v9.9.9", workspace)


class TestListVersions:
    def test_empty_for_unknown(self, workspace: Path) -> None:
        assert pm.list_versions("nobody", workspace) == []

    def test_versions_ordered(self, workspace: Path) -> None:
        for _ in range(3):
            pm.save_prompt("p", "x", base=workspace)
        assert pm.list_versions("p", workspace) == ["v0.0.1", "v0.0.2", "v0.0.3"]


class TestListPrompts:
    def test_empty(self, workspace: Path) -> None:
        assert pm.list_prompts(workspace) == []

    def test_returns_current_version(self, workspace: Path) -> None:
        pm.save_prompt("a", "content a", base=workspace)
        pm.save_prompt("b", "content b", base=workspace)
        prompts = pm.list_prompts(workspace)
        names = [p["name"] for p in prompts]
        assert "a" in names
        assert "b" in names


class TestDeletePrompt:
    def test_delete_all(self, workspace: Path) -> None:
        pm.save_prompt("p", "x", base=workspace)
        pm.delete_prompt("p", base=workspace)
        assert not pm.prompt_dir("p", workspace).exists()

    def test_delete_specific_version(self, workspace: Path) -> None:
        pm.save_prompt("p", "v1", base=workspace)
        pm.save_prompt("p", "v2", base=workspace)
        pm.delete_prompt("p", "v0.0.1", workspace)
        assert pm.list_versions("p", workspace) == ["v0.0.2"]

    def test_delete_current_version_updates_current(self, workspace: Path) -> None:
        pm.save_prompt("p", "v1", base=workspace)
        pm.save_prompt("p", "v2", base=workspace)
        pm.delete_prompt("p", "v0.0.2", workspace)
        assert pm.get_current_version("p", workspace) == "v0.0.1"

    def test_delete_missing_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            pm.delete_prompt("ghost", base=workspace)

    def test_delete_missing_version_raises(self, workspace: Path) -> None:
        pm.save_prompt("p", "x", base=workspace)
        with pytest.raises(FileNotFoundError):
            pm.delete_prompt("p", "v9.9.9", workspace)


class TestDiffPrompts:
    def test_no_diff_identical(self, workspace: Path) -> None:
        pm.save_prompt("p", "same\n", base=workspace)
        pm.save_prompt("p", "same\n", base=workspace)
        lines = pm.diff_prompts("p", "v0.0.1", "p", "v0.0.2", workspace)
        assert lines == []

    def test_diff_shows_changes(self, workspace: Path) -> None:
        pm.save_prompt("p", "line one\n", base=workspace)
        pm.save_prompt("p", "line two\n", base=workspace)
        lines = pm.diff_prompts("p", "v0.0.1", "p", "v0.0.2", workspace)
        assert any("-line one" in l for l in lines)
        assert any("+line two" in l for l in lines)


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestPromptSaveCLI:
    def test_save_with_content(self, workspace: Path) -> None:
        result = runner.invoke(app, ["prompt", "save", "test", "--content", "hello world"])
        assert result.exit_code == 0, result.output
        assert "v0.0.1" in result.output

    def test_save_with_file(self, workspace: Path, tmp_path: Path) -> None:
        f = workspace / "myprompt.txt"
        f.write_text("file content", encoding="utf-8")
        result = runner.invoke(app, ["prompt", "save", "fromfile", "--file", str(f)])
        assert result.exit_code == 0, result.output
        assert "v0.0.1" in result.output

    def test_save_increments_version(self, workspace: Path) -> None:
        runner.invoke(app, ["prompt", "save", "p", "--content", "v1"])
        result = runner.invoke(app, ["prompt", "save", "p", "--content", "v2"])
        assert "v0.0.2" in result.output

    def test_save_with_description_and_tags(self, workspace: Path) -> None:
        result = runner.invoke(
            app,
            ["prompt", "save", "p", "--content", "x", "--description", "my desc", "--tags", "a,b"],
        )
        assert result.exit_code == 0
        data = pm.load_prompt("p", base=workspace)
        assert data["description"] == "my desc"
        assert data["tags"] == ["a", "b"]

    def test_save_no_content_fails(self, workspace: Path) -> None:
        result = runner.invoke(app, ["prompt", "save", "p"])
        assert result.exit_code != 0

    def test_save_not_initialized_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["prompt", "save", "p", "--content", "x"])
        assert result.exit_code != 0


class TestPromptShowCLI:
    def test_show_current(self, workspace: Path) -> None:
        pm.save_prompt("p", "hello prompt", base=workspace)
        result = runner.invoke(app, ["prompt", "show", "p"])
        assert result.exit_code == 0
        assert "hello prompt" in result.output

    def test_show_specific_version(self, workspace: Path) -> None:
        pm.save_prompt("p", "first", base=workspace)
        pm.save_prompt("p", "second", base=workspace)
        result = runner.invoke(app, ["prompt", "show", "p@v0.0.1"])
        assert result.exit_code == 0
        assert "first" in result.output

    def test_show_missing_fails(self, workspace: Path) -> None:
        result = runner.invoke(app, ["prompt", "show", "ghost"])
        assert result.exit_code != 0


class TestPromptListCLI:
    def test_list_empty(self, workspace: Path) -> None:
        result = runner.invoke(app, ["prompt", "list"])
        assert result.exit_code == 0
        assert "No prompts" in result.output

    def test_list_shows_prompts(self, workspace: Path) -> None:
        pm.save_prompt("alpha", "c", description="my alpha", base=workspace)
        pm.save_prompt("beta", "c", base=workspace)
        result = runner.invoke(app, ["prompt", "list"])
        assert result.exit_code == 0
        assert "alpha" in result.output
        assert "beta" in result.output


class TestPromptHistoryCLI:
    def test_history_shows_versions(self, workspace: Path) -> None:
        pm.save_prompt("p", "v1", base=workspace)
        pm.save_prompt("p", "v2", base=workspace)
        pm.save_prompt("p", "v3", base=workspace)
        result = runner.invoke(app, ["prompt", "history", "p"])
        assert result.exit_code == 0
        assert "v0.0.1" in result.output
        assert "v0.0.3" in result.output
        assert "current" in result.output

    def test_history_missing_fails(self, workspace: Path) -> None:
        result = runner.invoke(app, ["prompt", "history", "ghost"])
        assert result.exit_code != 0


class TestPromptDiffCLI:
    def test_diff_shows_changes(self, workspace: Path) -> None:
        pm.save_prompt("p", "line one\n", base=workspace)
        pm.save_prompt("p", "line two\n", base=workspace)
        result = runner.invoke(app, ["prompt", "diff", "p@v0.0.1", "p@v0.0.2"])
        assert result.exit_code == 0
        assert "line one" in result.output
        assert "line two" in result.output

    def test_diff_no_changes(self, workspace: Path) -> None:
        pm.save_prompt("p", "same\n", base=workspace)
        pm.save_prompt("p", "same\n", base=workspace)
        result = runner.invoke(app, ["prompt", "diff", "p@v0.0.1", "p@v0.0.2"])
        assert result.exit_code == 0
        assert "No differences" in result.output

    def test_diff_missing_ref_fails(self, workspace: Path) -> None:
        result = runner.invoke(app, ["prompt", "diff", "ghost@v0.0.1", "ghost@v0.0.2"])
        assert result.exit_code != 0


class TestPromptDeleteCLI:
    def test_delete_prompt(self, workspace: Path) -> None:
        pm.save_prompt("p", "x", base=workspace)
        result = runner.invoke(app, ["prompt", "delete", "p", "--yes"])
        assert result.exit_code == 0
        assert not pm.prompt_dir("p", workspace).exists()

    def test_delete_specific_version(self, workspace: Path) -> None:
        pm.save_prompt("p", "v1", base=workspace)
        pm.save_prompt("p", "v2", base=workspace)
        result = runner.invoke(app, ["prompt", "delete", "p@v0.0.1", "--yes"])
        assert result.exit_code == 0
        assert pm.list_versions("p", workspace) == ["v0.0.2"]

    def test_delete_missing_fails(self, workspace: Path) -> None:
        result = runner.invoke(app, ["prompt", "delete", "ghost", "--yes"])
        assert result.exit_code != 0
