"""Tests for Phase 1.3: schema asset management."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit import schema as sm

runner = CliRunner()

VALID_PARAMS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "File path"}
    },
    "required": ["path"],
}

INVALID_PARAMS = {
    "type": "not-a-real-type",
    "properties": "should-be-an-object",
}


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
# Unit tests — schema module
# ---------------------------------------------------------------------------


class TestVersionHelpers:
    def test_parse_version(self) -> None:
        from harness_kit.schema import _parse_version
        assert _parse_version("v1.2.3") == (1, 2, 3)
        assert _parse_version("v0.0.1") == (0, 0, 1)

    def test_bump_patch(self) -> None:
        from harness_kit.schema import _bump_patch
        assert _bump_patch("v0.0.1") == "v0.0.2"
        assert _bump_patch("v1.2.9") == "v1.2.10"


class TestSaveSchema:
    def test_first_save_creates_v001(self, workspace: Path) -> None:
        ver, is_new = sm.save_schema("read-file", VALID_PARAMS, base=workspace)
        assert ver == "v0.0.1"
        assert is_new is True

    def test_second_save_bumps_patch(self, workspace: Path) -> None:
        sm.save_schema("read-file", VALID_PARAMS, base=workspace)
        ver, is_new = sm.save_schema("read-file", VALID_PARAMS, base=workspace)
        assert ver == "v0.0.2"
        assert is_new is False

    def test_current_file_updated(self, workspace: Path) -> None:
        sm.save_schema("read-file", VALID_PARAMS, base=workspace)
        sm.save_schema("read-file", VALID_PARAMS, base=workspace)
        assert sm.get_current_version("read-file", workspace) == "v0.0.2"

    def test_json_file_created(self, workspace: Path) -> None:
        sm.save_schema("read-file", VALID_PARAMS, description="Read a file", base=workspace)
        vf = workspace / ".harness" / "schemas" / "read-file" / "v0.0.1.json"
        assert vf.exists()
        data = json.loads(vf.read_text())
        assert data["parameters"] == VALID_PARAMS
        assert data["description"] == "Read a file"
        assert data["version"] == "v0.0.1"
        assert data["name"] == "read-file"

    def test_tags_stored(self, workspace: Path) -> None:
        sm.save_schema("s", VALID_PARAMS, tags=["file", "io"], base=workspace)
        data = sm.load_schema("s", base=workspace)
        assert data["tags"] == ["file", "io"]

    def test_parameters_preserved(self, workspace: Path) -> None:
        sm.save_schema("s", VALID_PARAMS, base=workspace)
        data = sm.load_schema("s", base=workspace)
        assert data["parameters"] == VALID_PARAMS


class TestLoadSchema:
    def test_load_current(self, workspace: Path) -> None:
        sm.save_schema("s", VALID_PARAMS, base=workspace)
        data = sm.load_schema("s", base=workspace)
        assert data["parameters"] == VALID_PARAMS

    def test_load_specific_version(self, workspace: Path) -> None:
        params_v1 = {"type": "object", "properties": {"x": {"type": "string"}}}
        params_v2 = {"type": "object", "properties": {"y": {"type": "integer"}}}
        sm.save_schema("s", params_v1, base=workspace)
        sm.save_schema("s", params_v2, base=workspace)
        data = sm.load_schema("s", "v0.0.1", workspace)
        assert data["parameters"] == params_v1

    def test_load_missing_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            sm.load_schema("missing", base=workspace)

    def test_load_missing_version_raises(self, workspace: Path) -> None:
        sm.save_schema("s", VALID_PARAMS, base=workspace)
        with pytest.raises(FileNotFoundError):
            sm.load_schema("s", "v9.9.9", workspace)


class TestListVersions:
    def test_empty_for_unknown(self, workspace: Path) -> None:
        assert sm.list_versions("nobody", workspace) == []

    def test_versions_ordered(self, workspace: Path) -> None:
        for _ in range(3):
            sm.save_schema("s", VALID_PARAMS, base=workspace)
        assert sm.list_versions("s", workspace) == ["v0.0.1", "v0.0.2", "v0.0.3"]


class TestListSchemas:
    def test_empty(self, workspace: Path) -> None:
        assert sm.list_schemas(workspace) == []

    def test_returns_current_version(self, workspace: Path) -> None:
        sm.save_schema("alpha", VALID_PARAMS, base=workspace)
        sm.save_schema("beta", VALID_PARAMS, base=workspace)
        schemas = sm.list_schemas(workspace)
        names = [s["name"] for s in schemas]
        assert "alpha" in names
        assert "beta" in names


class TestDeleteSchema:
    def test_delete_all(self, workspace: Path) -> None:
        sm.save_schema("s", VALID_PARAMS, base=workspace)
        sm.delete_schema("s", base=workspace)
        assert not sm.schema_dir("s", workspace).exists()

    def test_delete_specific_version(self, workspace: Path) -> None:
        sm.save_schema("s", VALID_PARAMS, base=workspace)
        sm.save_schema("s", VALID_PARAMS, base=workspace)
        sm.delete_schema("s", "v0.0.1", workspace)
        assert sm.list_versions("s", workspace) == ["v0.0.2"]

    def test_delete_current_version_updates_current(self, workspace: Path) -> None:
        sm.save_schema("s", VALID_PARAMS, base=workspace)
        sm.save_schema("s", VALID_PARAMS, base=workspace)
        sm.delete_schema("s", "v0.0.2", workspace)
        assert sm.get_current_version("s", workspace) == "v0.0.1"

    def test_delete_missing_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            sm.delete_schema("ghost", base=workspace)

    def test_delete_missing_version_raises(self, workspace: Path) -> None:
        sm.save_schema("s", VALID_PARAMS, base=workspace)
        with pytest.raises(FileNotFoundError):
            sm.delete_schema("s", "v9.9.9", workspace)


class TestValidateSchema:
    def test_valid_schema_returns_no_errors(self, workspace: Path) -> None:
        sm.save_schema("s", VALID_PARAMS, base=workspace)
        errors = sm.validate_schema("s", workspace)
        assert errors == []

    def test_invalid_type_returns_error(self, workspace: Path) -> None:
        sm.save_schema("s", INVALID_PARAMS, base=workspace)
        errors = sm.validate_schema("s", workspace)
        assert len(errors) > 0

    def test_missing_schema_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            sm.validate_schema("ghost", workspace)

    def test_missing_parameters_field(self, workspace: Path) -> None:
        # Manually write a schema without 'parameters'
        d = sm.schema_dir("s", workspace)
        d.mkdir(parents=True, exist_ok=True)
        vf = d / "v0.0.1.json"
        vf.write_text(json.dumps({"name": "s", "version": "v0.0.1"}))
        (d / "_current").write_text("v0.0.1")
        errors = sm.validate_schema("s", workspace)
        assert any("parameters" in e.lower() for e in errors)

    def test_empty_parameters_is_valid(self, workspace: Path) -> None:
        # {} is a valid JSON Schema (accepts everything)
        sm.save_schema("s", {}, base=workspace)
        errors = sm.validate_schema("s", workspace)
        assert errors == []


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestSchemaSaveCLI:
    def test_save_with_file(self, workspace: Path) -> None:
        f = workspace / "schema.json"
        f.write_text(json.dumps({"parameters": VALID_PARAMS}))
        result = runner.invoke(app, ["schema", "save", "test", "--file", str(f)])
        assert result.exit_code == 0, result.output
        assert "v0.0.1" in result.output

    def test_save_increments_version(self, workspace: Path) -> None:
        f = workspace / "schema.json"
        f.write_text(json.dumps({"parameters": VALID_PARAMS}))
        runner.invoke(app, ["schema", "save", "s", "--file", str(f)])
        result = runner.invoke(app, ["schema", "save", "s", "--file", str(f)])
        assert "v0.0.2" in result.output

    def test_save_bare_parameters(self, workspace: Path) -> None:
        # File is just the parameters object itself (no wrapper)
        f = workspace / "schema.json"
        f.write_text(json.dumps(VALID_PARAMS))
        result = runner.invoke(app, ["schema", "save", "bare", "--file", str(f)])
        assert result.exit_code == 0, result.output

    def test_save_invalid_json_fails(self, workspace: Path) -> None:
        f = workspace / "schema.json"
        f.write_text("this is not json")
        result = runner.invoke(app, ["schema", "save", "bad", "--file", str(f)])
        assert result.exit_code != 0

    def test_save_no_file_fails(self, workspace: Path) -> None:
        result = runner.invoke(app, ["schema", "save", "s"])
        assert result.exit_code != 0

    def test_save_not_initialized_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["schema", "save", "s"])
        assert result.exit_code != 0


class TestSchemaShowCLI:
    def test_show_current(self, workspace: Path) -> None:
        sm.save_schema("s", VALID_PARAMS, base=workspace)
        result = runner.invoke(app, ["schema", "show", "s"])
        assert result.exit_code == 0
        assert "path" in result.output

    def test_show_specific_version(self, workspace: Path) -> None:
        params_v1 = {"type": "object", "properties": {"x": {"type": "string"}}}
        sm.save_schema("s", params_v1, base=workspace)
        sm.save_schema("s", VALID_PARAMS, base=workspace)
        result = runner.invoke(app, ["schema", "show", "s@v0.0.1"])
        assert result.exit_code == 0
        assert '"x"' in result.output

    def test_show_missing_fails(self, workspace: Path) -> None:
        result = runner.invoke(app, ["schema", "show", "ghost"])
        assert result.exit_code != 0


class TestSchemaListCLI:
    def test_list_empty(self, workspace: Path) -> None:
        result = runner.invoke(app, ["schema", "list"])
        assert result.exit_code == 0
        assert "No schemas" in result.output

    def test_list_shows_schemas(self, workspace: Path) -> None:
        sm.save_schema("alpha", VALID_PARAMS, description="schema alpha", base=workspace)
        sm.save_schema("beta", VALID_PARAMS, base=workspace)
        result = runner.invoke(app, ["schema", "list"])
        assert result.exit_code == 0
        assert "alpha" in result.output
        assert "beta" in result.output


class TestSchemaValidateCLI:
    def test_validate_valid(self, workspace: Path) -> None:
        sm.save_schema("s", VALID_PARAMS, base=workspace)
        result = runner.invoke(app, ["schema", "validate", "s"])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_validate_invalid(self, workspace: Path) -> None:
        sm.save_schema("s", INVALID_PARAMS, base=workspace)
        result = runner.invoke(app, ["schema", "validate", "s"])
        assert result.exit_code != 0

    def test_validate_missing_fails(self, workspace: Path) -> None:
        result = runner.invoke(app, ["schema", "validate", "ghost"])
        assert result.exit_code != 0


class TestSchemaDeleteCLI:
    def test_delete_schema(self, workspace: Path) -> None:
        sm.save_schema("s", VALID_PARAMS, base=workspace)
        result = runner.invoke(app, ["schema", "delete", "s", "--yes"])
        assert result.exit_code == 0
        assert not sm.schema_dir("s", workspace).exists()

    def test_delete_specific_version(self, workspace: Path) -> None:
        sm.save_schema("s", VALID_PARAMS, base=workspace)
        sm.save_schema("s", VALID_PARAMS, base=workspace)
        result = runner.invoke(app, ["schema", "delete", "s@v0.0.1", "--yes"])
        assert result.exit_code == 0
        assert sm.list_versions("s", workspace) == ["v0.0.2"]

    def test_delete_missing_fails(self, workspace: Path) -> None:
        result = runner.invoke(app, ["schema", "delete", "ghost", "--yes"])
        assert result.exit_code != 0
