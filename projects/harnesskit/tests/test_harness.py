"""Tests for Phase 3.1: Harness data model, storage, and CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit import harness as hm
from harness_kit import skill as sm

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_HARNESS: dict = {
    "name": "my-code-review",
    "description": "完整的代码审查 Harness",
    "skills": ["code-reviewer@v0.1.0", "explain-error@v0.0.2"],
    "model": {
        "provider": "openai",
        "name": "gpt-4o",
        "temperature": 0.3,
        "max_tokens": 2000,
    },
    "memory": {
        "scope": "session",
        "max_turns": 10,
    },
    "constraints": {
        "rules": [],
        "max_cost_per_call": 0.01,
        "timeout": 30,
    },
    "context_budget": 4000,
    "changelog": "首个版本",
}


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Initialised .harness workspace in tmp_path."""
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Unit tests: harness module
# ---------------------------------------------------------------------------


class TestHarnessValidation:
    def test_valid_harness(self) -> None:
        errors = hm._validate_harness_data(SAMPLE_HARNESS)
        assert errors == []

    def test_missing_name(self) -> None:
        data = {**SAMPLE_HARNESS, "name": ""}
        errors = hm._validate_harness_data(data)
        assert any("name" in e for e in errors)

    def test_missing_description(self) -> None:
        data = {**SAMPLE_HARNESS, "description": ""}
        errors = hm._validate_harness_data(data)
        assert any("description" in e for e in errors)

    def test_invalid_memory_scope(self) -> None:
        data = {**SAMPLE_HARNESS, "memory": {"scope": "invalid"}}
        errors = hm._validate_harness_data(data)
        assert any("scope" in e for e in errors)

    def test_valid_memory_scopes(self) -> None:
        for scope in ("session", "harness", "global"):
            data = {**SAMPLE_HARNESS, "memory": {"scope": scope}}
            errors = hm._validate_harness_data(data)
            assert errors == [], f"scope '{scope}' should be valid"

    def test_invalid_context_budget(self) -> None:
        data = {**SAMPLE_HARNESS, "context_budget": -100}
        errors = hm._validate_harness_data(data)
        assert any("context_budget" in e for e in errors)

    def test_skills_must_be_list(self) -> None:
        data = {**SAMPLE_HARNESS, "skills": "not-a-list"}
        errors = hm._validate_harness_data(data)
        assert any("skills" in e for e in errors)

    def test_model_must_be_dict(self) -> None:
        data = {**SAMPLE_HARNESS, "model": "gpt-4o"}
        errors = hm._validate_harness_data(data)
        assert any("model" in e for e in errors)


class TestHarnessCRUD:
    def test_save_and_load(self, workspace: Path) -> None:
        version, is_new = hm.save_harness(
            name="my-harness",
            description="Test harness",
            skills=["skill-a@v0.1.0"],
            base=workspace,
        )
        assert is_new is True
        assert version == "v0.0.1"

        data = hm.load_harness("my-harness", base=workspace)
        assert data["name"] == "my-harness"
        assert data["description"] == "Test harness"
        assert data["skills"] == ["skill-a@v0.1.0"]
        assert data["version"] == "v0.0.1"

    def test_auto_increment_patch(self, workspace: Path) -> None:
        hm.save_harness("my-harness", description="v1", base=workspace)
        v2, _ = hm.save_harness("my-harness", description="v2", base=workspace)
        assert v2 == "v0.0.2"

    def test_current_file_updated(self, workspace: Path) -> None:
        hm.save_harness("h1", description="first", base=workspace)
        hm.save_harness("h1", description="second", base=workspace)
        current = hm.get_current_version("h1", workspace)
        assert current == "v0.0.2"

    def test_load_specific_version(self, workspace: Path) -> None:
        hm.save_harness("h1", description="first", base=workspace)
        hm.save_harness("h1", description="second", base=workspace)

        v1 = hm.load_harness("h1", "v0.0.1", workspace)
        assert v1["description"] == "first"

        v2 = hm.load_harness("h1", "v0.0.2", workspace)
        assert v2["description"] == "second"

    def test_load_nonexistent_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            hm.load_harness("nonexistent", base=workspace)

    def test_list_harnesses(self, workspace: Path) -> None:
        hm.save_harness("h1", description="first harness", base=workspace)
        hm.save_harness("h2", description="second harness", base=workspace)

        harnesses = hm.list_harnesses(workspace)
        names = [h["name"] for h in harnesses]
        assert "h1" in names
        assert "h2" in names

    def test_list_empty(self, workspace: Path) -> None:
        assert hm.list_harnesses(workspace) == []

    def test_delete_entire_harness(self, workspace: Path) -> None:
        hm.save_harness("h1", description="to delete", base=workspace)
        hm.delete_harness("h1", base=workspace)

        with pytest.raises(FileNotFoundError):
            hm.load_harness("h1", base=workspace)

    def test_delete_specific_version(self, workspace: Path) -> None:
        hm.save_harness("h1", description="v1", base=workspace)
        hm.save_harness("h1", description="v2", base=workspace)

        hm.delete_harness("h1", "v0.0.1", workspace)
        versions = hm.list_versions("h1", workspace)
        assert "v0.0.1" not in versions
        assert "v0.0.2" in versions

    def test_delete_nonexistent_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            hm.delete_harness("nonexistent", base=workspace)

    def test_save_from_dict(self, workspace: Path) -> None:
        version, is_new = hm.save_harness_from_dict(SAMPLE_HARNESS, workspace)
        assert is_new is True
        data = hm.load_harness("my-code-review", base=workspace)
        assert data["skills"] == ["code-reviewer@v0.1.0", "explain-error@v0.0.2"]
        assert data["model"]["name"] == "gpt-4o"

    def test_save_from_dict_missing_name(self, workspace: Path) -> None:
        data = {k: v for k, v in SAMPLE_HARNESS.items() if k != "name"}
        with pytest.raises(ValueError, match="'name' field"):
            hm.save_harness_from_dict(data, workspace)

    def test_storage_path(self, workspace: Path) -> None:
        hm.save_harness("my-harness", description="test", base=workspace)
        expected = workspace / ".harness" / "harnesses" / "my-harness" / "v0.0.1.yaml"
        assert expected.exists()
        current_file = workspace / ".harness" / "harnesses" / "my-harness" / "_current"
        assert current_file.read_text().strip() == "v0.0.1"


class TestHarnessDiff:
    def test_diff_two_versions(self, workspace: Path) -> None:
        hm.save_harness("h1", description="first version", skills=["s1"], base=workspace)
        hm.save_harness("h1", description="second version", skills=["s1", "s2"], base=workspace)
        lines = hm.diff_harnesses("h1", "v0.0.1", "h1", "v0.0.2", workspace)
        assert len(lines) > 0
        added = [l for l in lines if l.startswith("+")]
        removed = [l for l in lines if l.startswith("-")]
        assert any("s2" in l for l in added)
        assert any("first" in l for l in removed)

    def test_diff_same_version_is_empty(self, workspace: Path) -> None:
        hm.save_harness("h1", description="same", base=workspace)
        lines = hm.diff_harnesses("h1", "v0.0.1", "h1", "v0.0.1", workspace)
        assert lines == []


class TestHarnessClone:
    def test_clone_resets_version(self, workspace: Path) -> None:
        hm.save_harness("original", description="orig", skills=["s1"], base=workspace)
        hm.save_harness("original", description="orig v2", skills=["s1"], base=workspace)

        new_ver = hm.clone_harness("original", "cloned", workspace)
        assert new_ver == "v0.0.1"

        cloned = hm.load_harness("cloned", base=workspace)
        assert cloned["name"] == "cloned"
        assert cloned["version"] == "v0.0.1"
        assert cloned["skills"] == ["s1"]

    def test_clone_nonexistent_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            hm.clone_harness("nonexistent", "new", workspace)

    def test_clone_to_existing_raises(self, workspace: Path) -> None:
        hm.save_harness("h1", description="first", base=workspace)
        hm.save_harness("h2", description="second", base=workspace)
        with pytest.raises(FileExistsError):
            hm.clone_harness("h1", "h2", workspace)


class TestHarnessReferenceValidation:
    def test_valid_references(self, workspace: Path) -> None:
        # Create a skill first
        sm.save_skill("my-skill", description="test skill", base=workspace)
        hm.save_harness(
            "my-harness",
            description="test",
            skills=["my-skill@v0.0.1"],
            base=workspace,
        )
        errors = hm.validate_harness_references("my-harness", base=workspace)
        assert errors == []

    def test_broken_skill_reference(self, workspace: Path) -> None:
        hm.save_harness(
            "my-harness",
            description="test",
            skills=["nonexistent-skill@v0.1.0"],
            base=workspace,
        )
        errors = hm.validate_harness_references("my-harness", base=workspace)
        assert any("nonexistent-skill" in e for e in errors)

    def test_empty_skills_list_is_valid(self, workspace: Path) -> None:
        hm.save_harness("my-harness", description="test", skills=[], base=workspace)
        errors = hm.validate_harness_references("my-harness", base=workspace)
        assert errors == []

    def test_harness_not_found_returns_error(self, workspace: Path) -> None:
        errors = hm.validate_harness_references("nonexistent", base=workspace)
        assert any("nonexistent" in e for e in errors)

    def test_multiple_skill_refs(self, workspace: Path) -> None:
        sm.save_skill("skill-a", description="skill a", base=workspace)
        sm.save_skill("skill-b", description="skill b", base=workspace)
        hm.save_harness(
            "multi-harness",
            description="test",
            skills=["skill-a", "skill-b", "missing-skill"],
            base=workspace,
        )
        errors = hm.validate_harness_references("multi-harness", base=workspace)
        assert len(errors) == 1
        assert "missing-skill" in errors[0]


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestHarnessCLI:
    def test_create_basic(self, workspace: Path) -> None:
        result = runner.invoke(
            app,
            ["harness", "create", "test-harness", "--description", "A test harness"],
        )
        assert result.exit_code == 0, result.output
        assert "Created" in result.output
        assert "test-harness" in result.output
        assert "v0.0.1" in result.output

    def test_create_with_skills(self, workspace: Path) -> None:
        result = runner.invoke(
            app,
            [
                "harness", "create", "test-harness",
                "--description", "Test",
                "--skills", "skill-a@v0.1.0,skill-b",
            ],
        )
        assert result.exit_code == 0, result.output
        data = hm.load_harness("test-harness", base=workspace)
        assert "skill-a@v0.1.0" in data["skills"]
        assert "skill-b" in data["skills"]

    def test_create_from_file(self, workspace: Path, tmp_path: Path) -> None:
        yaml_file = workspace / "harness_def.yaml"
        yaml_file.write_text(
            yaml.dump(SAMPLE_HARNESS, allow_unicode=True),
            encoding="utf-8",
        )
        result = runner.invoke(
            app,
            ["harness", "create", "my-code-review", "--file", str(yaml_file)],
        )
        assert result.exit_code == 0, result.output
        assert "v0.0.1" in result.output

    def test_create_increments_version(self, workspace: Path) -> None:
        runner.invoke(app, ["harness", "create", "h1", "--description", "v1"])
        result = runner.invoke(app, ["harness", "create", "h1", "--description", "v2"])
        assert result.exit_code == 0, result.output
        assert "v0.0.2" in result.output

    def test_show_harness(self, workspace: Path) -> None:
        runner.invoke(
            app,
            [
                "harness", "create", "my-harness",
                "--description", "Test harness",
                "--skills", "skill-x",
                "--model", "gpt-4o",
            ],
        )
        result = runner.invoke(app, ["harness", "show", "my-harness"])
        assert result.exit_code == 0, result.output
        assert "my-harness" in result.output
        assert "Test harness" in result.output
        assert "gpt-4o" in result.output

    def test_show_nonexistent(self, workspace: Path) -> None:
        result = runner.invoke(app, ["harness", "show", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_list_harnesses(self, workspace: Path) -> None:
        runner.invoke(app, ["harness", "create", "h1", "--description", "First"])
        runner.invoke(app, ["harness", "create", "h2", "--description", "Second"])
        result = runner.invoke(app, ["harness", "list"])
        assert result.exit_code == 0, result.output
        assert "h1" in result.output
        assert "h2" in result.output

    def test_list_empty(self, workspace: Path) -> None:
        result = runner.invoke(app, ["harness", "list"])
        assert result.exit_code == 0, result.output
        assert "No harnesses" in result.output

    def test_diff_two_versions(self, workspace: Path) -> None:
        runner.invoke(app, ["harness", "create", "h1", "--description", "first", "--skills", "s1"])
        runner.invoke(app, ["harness", "create", "h1", "--description", "second", "--skills", "s2"])
        result = runner.invoke(app, ["harness", "diff", "h1@v0.0.1", "h1@v0.0.2"])
        assert result.exit_code == 0, result.output
        assert "first" in result.output or "second" in result.output

    def test_clone_harness(self, workspace: Path) -> None:
        runner.invoke(app, ["harness", "create", "original", "--description", "orig"])
        result = runner.invoke(app, ["harness", "clone", "original", "cloned"])
        assert result.exit_code == 0, result.output
        assert "Cloned" in result.output
        cloned = hm.load_harness("cloned", base=workspace)
        assert cloned["name"] == "cloned"

    def test_validate_valid(self, workspace: Path) -> None:
        runner.invoke(app, ["harness", "create", "h1", "--description", "test"])
        result = runner.invoke(app, ["harness", "validate", "h1"])
        assert result.exit_code == 0, result.output
        assert "valid" in result.output.lower()

    def test_validate_broken_ref(self, workspace: Path) -> None:
        runner.invoke(
            app,
            ["harness", "create", "h1", "--description", "test", "--skills", "missing-skill"],
        )
        result = runner.invoke(app, ["harness", "validate", "h1"])
        assert result.exit_code == 1
        assert "missing-skill" in result.output

    def test_delete_harness_with_yes(self, workspace: Path) -> None:
        runner.invoke(app, ["harness", "create", "h1", "--description", "to delete"])
        result = runner.invoke(app, ["harness", "delete", "h1", "--yes"])
        assert result.exit_code == 0, result.output
        assert "Deleted" in result.output
        with pytest.raises(FileNotFoundError):
            hm.load_harness("h1", base=workspace)

    def test_delete_nonexistent(self, workspace: Path) -> None:
        result = runner.invoke(app, ["harness", "delete", "nonexistent", "--yes"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_create_without_init(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["harness", "create", "h1", "--description", "test"])
        assert result.exit_code == 1
        assert "init" in result.output.lower()

    def test_show_specific_version(self, workspace: Path) -> None:
        runner.invoke(app, ["harness", "create", "h1", "--description", "version one"])
        runner.invoke(app, ["harness", "create", "h1", "--description", "version two"])
        result = runner.invoke(app, ["harness", "show", "h1@v0.0.1"])
        assert result.exit_code == 0, result.output
        assert "v0.0.1" in result.output

    def test_harness_model_config_stored(self, workspace: Path) -> None:
        runner.invoke(
            app,
            [
                "harness", "create", "h1",
                "--description", "test",
                "--model", "claude-3-5-sonnet",
                "--temperature", "0.3",
                "--max-tokens", "4096",
            ],
        )
        data = hm.load_harness("h1", base=workspace)
        assert data["model"]["name"] == "claude-3-5-sonnet"
        assert data["model"]["temperature"] == 0.3
        assert data["model"]["max_tokens"] == 4096

    def test_harness_memory_config_stored(self, workspace: Path) -> None:
        runner.invoke(
            app,
            [
                "harness", "create", "h1",
                "--description", "test",
                "--memory-scope", "harness",
                "--max-turns", "20",
            ],
        )
        data = hm.load_harness("h1", base=workspace)
        assert data["memory"]["scope"] == "harness"
        assert data["memory"]["max_turns"] == 20

    def test_multiple_skills_referenced(self, workspace: Path) -> None:
        """Acceptance criterion: can reference multiple Skills."""
        skills = ["code-reviewer@v0.1.0", "explain-error@v0.0.2", "summarize@v0.1.0"]
        runner.invoke(
            app,
            [
                "harness", "create", "multi-skill-harness",
                "--description", "Multi-skill test",
                "--skills", ",".join(skills),
            ],
        )
        data = hm.load_harness("multi-skill-harness", base=workspace)
        assert len(data["skills"]) == 3
        for s in skills:
            assert s in data["skills"]
