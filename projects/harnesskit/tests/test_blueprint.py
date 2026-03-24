"""Tests for Phase 4.1: Blueprint data model, storage, and CLI commands."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit import blueprint as bm

runner = CliRunner()

# ---------------------------------------------------------------------------
# Sample fixtures
# ---------------------------------------------------------------------------

SAMPLE_BLUEPRINT: dict = {
    "name": "code-review-pipeline",
    "description": "完整的代码审查流水线",
    "inputs": [
        {"name": "file_path", "required": True},
    ],
    "steps": [
        {
            "id": "lint",
            "type": "deterministic",
            "name": "代码格式检查",
            "run": "flake8 {{inputs.file_path}}",
            "on_fail": "stop",
            "timeout": 10,
        },
        {
            "id": "review",
            "type": "agentic",
            "name": "AI 代码审查",
            "harness": "my-code-review@v0.1.0",
            "inputs": {"code": "{{steps.lint.output}}"},
            "max_retries": 2,
            "timeout": 60,
        },
        {
            "id": "summary",
            "type": "agentic",
            "name": "生成摘要",
            "skill": "summarize@v0.1.0",
            "inputs": {"text": "{{steps.review.output}}"},
        },
    ],
    "outputs": {
        "lint_result": "{{steps.lint.output}}",
        "review_result": "{{steps.review.output}}",
        "summary": "{{steps.summary.output}}",
    },
    "changelog": "首个版本",
}


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Initialised .harness workspace in tmp_path."""
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Unit tests: blueprint module validation
# ---------------------------------------------------------------------------


class TestBlueprintValidation:
    def test_valid_blueprint(self) -> None:
        errors = bm._validate_blueprint_data(SAMPLE_BLUEPRINT)
        assert errors == []

    def test_missing_name(self) -> None:
        data = {**SAMPLE_BLUEPRINT, "name": ""}
        errors = bm._validate_blueprint_data(data)
        assert any("name" in e for e in errors)

    def test_missing_description(self) -> None:
        data = {**SAMPLE_BLUEPRINT, "description": ""}
        errors = bm._validate_blueprint_data(data)
        assert any("description" in e for e in errors)

    def test_missing_steps(self) -> None:
        data = {**SAMPLE_BLUEPRINT, "steps": []}
        errors = bm._validate_blueprint_data(data)
        assert any("steps" in e for e in errors)

    def test_steps_not_list(self) -> None:
        data = {**SAMPLE_BLUEPRINT, "steps": "not-a-list"}
        errors = bm._validate_blueprint_data(data)
        assert any("steps" in e for e in errors)

    def test_step_missing_id(self) -> None:
        bad_step = {"type": "deterministic", "run": "echo hi"}
        data = {**SAMPLE_BLUEPRINT, "steps": [bad_step]}
        errors = bm._validate_blueprint_data(data)
        assert any("id" in e for e in errors)

    def test_step_duplicate_id(self) -> None:
        steps = [
            {"id": "same", "type": "deterministic", "run": "echo 1"},
            {"id": "same", "type": "deterministic", "run": "echo 2"},
        ]
        data = {**SAMPLE_BLUEPRINT, "steps": steps}
        errors = bm._validate_blueprint_data(data)
        assert any("Duplicate" in e for e in errors)

    def test_step_invalid_type(self) -> None:
        steps = [{"id": "x", "type": "unknown", "run": "echo hi"}]
        data = {**SAMPLE_BLUEPRINT, "steps": steps}
        errors = bm._validate_blueprint_data(data)
        assert any("type" in e for e in errors)

    def test_deterministic_missing_run(self) -> None:
        steps = [{"id": "x", "type": "deterministic"}]
        data = {**SAMPLE_BLUEPRINT, "steps": steps}
        errors = bm._validate_blueprint_data(data)
        assert any("run" in e for e in errors)

    def test_agentic_missing_harness_and_skill(self) -> None:
        steps = [{"id": "x", "type": "agentic"}]
        data = {**SAMPLE_BLUEPRINT, "steps": steps}
        errors = bm._validate_blueprint_data(data)
        assert any("harness" in e or "skill" in e for e in errors)

    def test_agentic_with_harness_is_valid(self) -> None:
        steps = [{"id": "x", "type": "agentic", "harness": "my-harness"}]
        data = {**SAMPLE_BLUEPRINT, "steps": steps}
        errors = bm._validate_blueprint_data(data)
        assert errors == []

    def test_agentic_with_skill_is_valid(self) -> None:
        steps = [{"id": "x", "type": "agentic", "skill": "my-skill"}]
        data = {**SAMPLE_BLUEPRINT, "steps": steps}
        errors = bm._validate_blueprint_data(data)
        assert errors == []

    def test_invalid_on_fail(self) -> None:
        steps = [{"id": "x", "type": "deterministic", "run": "echo hi", "on_fail": "fly"}]
        data = {**SAMPLE_BLUEPRINT, "steps": steps}
        errors = bm._validate_blueprint_data(data)
        assert any("on_fail" in e for e in errors)

    def test_valid_on_fail_goto(self) -> None:
        steps = [
            {"id": "x", "type": "deterministic", "run": "echo hi", "on_fail": "goto:y"},
            {"id": "y", "type": "deterministic", "run": "echo bye"},
        ]
        data = {**SAMPLE_BLUEPRINT, "steps": steps}
        errors = bm._validate_blueprint_data(data)
        assert errors == []

    def test_invalid_timeout(self) -> None:
        steps = [{"id": "x", "type": "deterministic", "run": "echo hi", "timeout": -5}]
        data = {**SAMPLE_BLUEPRINT, "steps": steps}
        errors = bm._validate_blueprint_data(data)
        assert any("timeout" in e for e in errors)

    def test_outputs_not_dict(self) -> None:
        data = {**SAMPLE_BLUEPRINT, "outputs": ["not", "a", "dict"]}
        errors = bm._validate_blueprint_data(data)
        assert any("outputs" in e for e in errors)


# ---------------------------------------------------------------------------
# Unit tests: CRUD
# ---------------------------------------------------------------------------


class TestBlueprintCRUD:
    def test_save_creates_version_file(self, workspace: Path) -> None:
        version, is_new = bm.save_blueprint_from_dict(SAMPLE_BLUEPRINT, base=workspace)
        assert is_new is True
        assert version == "v0.0.1"
        vf = bm._version_file("code-review-pipeline", "v0.0.1", workspace)
        assert vf.exists()

    def test_save_writes_current_file(self, workspace: Path) -> None:
        bm.save_blueprint_from_dict(SAMPLE_BLUEPRINT, base=workspace)
        current = bm.get_current_version("code-review-pipeline", workspace)
        assert current == "v0.0.1"

    def test_save_bumps_patch_on_update(self, workspace: Path) -> None:
        bm.save_blueprint_from_dict(SAMPLE_BLUEPRINT, base=workspace)
        version2, is_new2 = bm.save_blueprint_from_dict(SAMPLE_BLUEPRINT, base=workspace)
        assert is_new2 is False
        assert version2 == "v0.0.2"

    def test_load_blueprint_by_name(self, workspace: Path) -> None:
        bm.save_blueprint_from_dict(SAMPLE_BLUEPRINT, base=workspace)
        data = bm.load_blueprint("code-review-pipeline", base=workspace)
        assert data["name"] == "code-review-pipeline"
        assert data["version"] == "v0.0.1"

    def test_load_blueprint_by_version(self, workspace: Path) -> None:
        bm.save_blueprint_from_dict(SAMPLE_BLUEPRINT, base=workspace)
        bm.save_blueprint_from_dict(SAMPLE_BLUEPRINT, base=workspace)
        data = bm.load_blueprint("code-review-pipeline", version="v0.0.1", base=workspace)
        assert data["version"] == "v0.0.1"

    def test_load_missing_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            bm.load_blueprint("nonexistent", base=workspace)

    def test_list_blueprints(self, workspace: Path) -> None:
        bm.save_blueprint_from_dict(SAMPLE_BLUEPRINT, base=workspace)
        bm.save_blueprint_from_dict({**SAMPLE_BLUEPRINT, "name": "other-bp"}, base=workspace)
        items = bm.list_blueprints(workspace)
        names = [i["name"] for i in items]
        assert "code-review-pipeline" in names
        assert "other-bp" in names

    def test_delete_blueprint_all_versions(self, workspace: Path) -> None:
        bm.save_blueprint_from_dict(SAMPLE_BLUEPRINT, base=workspace)
        bm.delete_blueprint("code-review-pipeline", base=workspace)
        assert not bm.blueprint_asset_dir("code-review-pipeline", workspace).exists()

    def test_delete_specific_version_updates_current(self, workspace: Path) -> None:
        bm.save_blueprint_from_dict(SAMPLE_BLUEPRINT, base=workspace)
        bm.save_blueprint_from_dict(SAMPLE_BLUEPRINT, base=workspace)
        # current is v0.0.2, delete it → current should revert to v0.0.1
        bm.delete_blueprint("code-review-pipeline", version="v0.0.2", base=workspace)
        current = bm.get_current_version("code-review-pipeline", workspace)
        assert current == "v0.0.1"

    def test_list_versions(self, workspace: Path) -> None:
        bm.save_blueprint_from_dict(SAMPLE_BLUEPRINT, base=workspace)
        bm.save_blueprint_from_dict(SAMPLE_BLUEPRINT, base=workspace)
        versions = bm.list_versions("code-review-pipeline", workspace)
        assert versions == ["v0.0.1", "v0.0.2"]

    def test_storage_path_structure(self, workspace: Path) -> None:
        bm.save_blueprint_from_dict(SAMPLE_BLUEPRINT, base=workspace)
        assert (workspace / ".harness" / "blueprints" / "code-review-pipeline").is_dir()
        assert (workspace / ".harness" / "blueprints" / "code-review-pipeline" / "v0.0.1.yaml").exists()
        assert (workspace / ".harness" / "blueprints" / "code-review-pipeline" / "_current").exists()


# ---------------------------------------------------------------------------
# Unit tests: variable reference validation
# ---------------------------------------------------------------------------


class TestBlueprintVariableRefs:
    def test_valid_refs_in_sample(self) -> None:
        errors = bm.validate_variable_refs(SAMPLE_BLUEPRINT)
        assert errors == []

    def test_unknown_step_ref(self) -> None:
        data = {
            **SAMPLE_BLUEPRINT,
            "outputs": {"result": "{{steps.missing.output}}"},
        }
        errors = bm.validate_variable_refs(data)
        assert any("missing" in e for e in errors)

    def test_unknown_input_ref(self) -> None:
        steps = [{"id": "x", "type": "deterministic", "run": "echo {{inputs.unknown}}"}]
        data = {**SAMPLE_BLUEPRINT, "steps": steps, "outputs": {}}
        errors = bm.validate_variable_refs(data)
        assert any("unknown" in e for e in errors)

    def test_valid_input_ref(self) -> None:
        steps = [
            {"id": "x", "type": "deterministic", "run": "echo {{inputs.file_path}}"}
        ]
        data = {**SAMPLE_BLUEPRINT, "steps": steps, "outputs": {}}
        errors = bm.validate_variable_refs(data)
        assert errors == []


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestBlueprintCLI:
    def test_create_from_file(self, workspace: Path, tmp_path: Path) -> None:
        yaml_file = tmp_path / "bp.yaml"
        yaml_file.write_text(
            yaml.dump(SAMPLE_BLUEPRINT, allow_unicode=True, default_flow_style=False)
        )
        result = runner.invoke(app, ["blueprint", "create", "code-review-pipeline", "--file", str(yaml_file)])
        assert result.exit_code == 0, result.output
        assert "Created" in result.output
        assert "v0.0.1" in result.output

    def test_create_minimal_inline(self, workspace: Path) -> None:
        # Minimal inline create should fail validation (empty steps)
        result = runner.invoke(app, ["blueprint", "create", "minimal", "--description", "test"])
        # empty steps list → validation error
        assert result.exit_code != 0 or "error" in result.output.lower()

    def test_show(self, workspace: Path, tmp_path: Path) -> None:
        yaml_file = tmp_path / "bp.yaml"
        yaml_file.write_text(
            yaml.dump(SAMPLE_BLUEPRINT, allow_unicode=True, default_flow_style=False)
        )
        runner.invoke(app, ["blueprint", "create", "code-review-pipeline", "--file", str(yaml_file)])
        result = runner.invoke(app, ["blueprint", "show", "code-review-pipeline"])
        assert result.exit_code == 0, result.output
        assert "code-review-pipeline" in result.output
        assert "lint" in result.output
        assert "review" in result.output

    def test_show_versioned(self, workspace: Path, tmp_path: Path) -> None:
        yaml_file = tmp_path / "bp.yaml"
        yaml_file.write_text(
            yaml.dump(SAMPLE_BLUEPRINT, allow_unicode=True, default_flow_style=False)
        )
        runner.invoke(app, ["blueprint", "create", "code-review-pipeline", "--file", str(yaml_file)])
        result = runner.invoke(app, ["blueprint", "show", "code-review-pipeline@v0.0.1"])
        assert result.exit_code == 0, result.output
        assert "v0.0.1" in result.output

    def test_list_empty(self, workspace: Path) -> None:
        result = runner.invoke(app, ["blueprint", "list"])
        assert result.exit_code == 0
        assert "No blueprints" in result.output

    def test_list_shows_blueprints(self, workspace: Path, tmp_path: Path) -> None:
        yaml_file = tmp_path / "bp.yaml"
        yaml_file.write_text(
            yaml.dump(SAMPLE_BLUEPRINT, allow_unicode=True, default_flow_style=False)
        )
        runner.invoke(app, ["blueprint", "create", "code-review-pipeline", "--file", str(yaml_file)])
        result = runner.invoke(app, ["blueprint", "list"])
        assert result.exit_code == 0
        assert "code-review-pipeline" in result.output

    def test_delete_with_yes(self, workspace: Path, tmp_path: Path) -> None:
        yaml_file = tmp_path / "bp.yaml"
        yaml_file.write_text(
            yaml.dump(SAMPLE_BLUEPRINT, allow_unicode=True, default_flow_style=False)
        )
        runner.invoke(app, ["blueprint", "create", "code-review-pipeline", "--file", str(yaml_file)])
        result = runner.invoke(app, ["blueprint", "delete", "code-review-pipeline", "--yes"])
        assert result.exit_code == 0, result.output
        assert "Deleted" in result.output

    def test_delete_nonexistent(self, workspace: Path) -> None:
        result = runner.invoke(app, ["blueprint", "delete", "nonexistent", "--yes"])
        assert result.exit_code != 0

    def test_validate_valid(self, workspace: Path, tmp_path: Path) -> None:
        yaml_file = tmp_path / "bp.yaml"
        yaml_file.write_text(
            yaml.dump(SAMPLE_BLUEPRINT, allow_unicode=True, default_flow_style=False)
        )
        runner.invoke(app, ["blueprint", "create", "code-review-pipeline", "--file", str(yaml_file)])
        result = runner.invoke(app, ["blueprint", "validate", "code-review-pipeline"])
        assert result.exit_code == 0, result.output
        assert "valid" in result.output.lower()

    def test_show_missing(self, workspace: Path) -> None:
        result = runner.invoke(app, ["blueprint", "show", "nonexistent"])
        assert result.exit_code != 0

    def test_diff(self, workspace: Path, tmp_path: Path) -> None:
        yaml_file = tmp_path / "bp.yaml"
        yaml_file.write_text(
            yaml.dump(SAMPLE_BLUEPRINT, allow_unicode=True, default_flow_style=False)
        )
        runner.invoke(app, ["blueprint", "create", "code-review-pipeline", "--file", str(yaml_file)])
        updated = {**SAMPLE_BLUEPRINT, "description": "Updated description"}
        yaml_file2 = tmp_path / "bp2.yaml"
        yaml_file2.write_text(
            yaml.dump(updated, allow_unicode=True, default_flow_style=False)
        )
        runner.invoke(app, ["blueprint", "create", "code-review-pipeline", "--file", str(yaml_file2)])
        result = runner.invoke(app, ["blueprint", "diff", "code-review-pipeline@v0.0.1", "code-review-pipeline@v0.0.2"])
        assert result.exit_code == 0, result.output

    def test_init_creates_blueprints_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / ".harness" / "blueprints").is_dir()
