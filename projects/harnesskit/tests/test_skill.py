"""Tests for Phase 2.1: skill data model and storage."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit import skill as sm

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SKILL: dict = {
    "name": "code-reviewer",
    "description": "审查代码，输出问题列表",
    "trigger": "当需要审查代码时",
    "inputs": [
        {"name": "code", "type": "string", "required": True},
        {"name": "language", "type": "string", "default": "auto"},
    ],
    "outputs": [
        {"name": "issues", "type": "array"},
    ],
    "assets": {
        "prompts": {
            "system": "code-reviewer-system@v0.1.0",
        },
        "rules": ["output-json", "no-hallucination"],
    },
    "examples": [
        {
            "input": {"code": "def foo(): pass", "language": "python"},
            "expected_contains": ["缺少实现"],
        }
    ],
    "changelog": "首个版本",
}


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Initialised .harness workspace in tmp_path."""
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


@pytest.fixture()
def skill_yaml(tmp_path: Path) -> Path:
    """Write a sample skill YAML to a temp file and return the path."""
    p = tmp_path / "code-reviewer.yaml"
    p.write_text(yaml.dump(SAMPLE_SKILL, allow_unicode=True), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Unit tests — version helpers
# ---------------------------------------------------------------------------


class TestVersionHelpers:
    def test_parse_version(self) -> None:
        assert sm._parse_version("v1.2.3") == (1, 2, 3)
        assert sm._parse_version("v0.0.1") == (0, 0, 1)

    def test_bump_patch(self) -> None:
        assert sm._bump_patch("v0.0.1") == "v0.0.2"
        assert sm._bump_patch("v1.2.9") == "v1.2.10"


# ---------------------------------------------------------------------------
# Unit tests — save_skill / save_skill_from_dict
# ---------------------------------------------------------------------------


class TestSaveSkill:
    def test_first_save_creates_v001(self, workspace: Path) -> None:
        ver, is_new = sm.save_skill(
            "my-skill", description="test", base=workspace
        )
        assert ver == "v0.0.1"
        assert is_new is True

    def test_second_save_bumps_patch(self, workspace: Path) -> None:
        sm.save_skill("my-skill", description="v1", base=workspace)
        ver, is_new = sm.save_skill("my-skill", description="v2", base=workspace)
        assert ver == "v0.0.2"
        assert is_new is False

    def test_current_file_updated(self, workspace: Path) -> None:
        sm.save_skill("my-skill", base=workspace)
        sm.save_skill("my-skill", base=workspace)
        assert sm.get_current_version("my-skill", workspace) == "v0.0.2"

    def test_yaml_file_created_at_correct_path(self, workspace: Path) -> None:
        sm.save_skill("my-skill", description="desc", base=workspace)
        vf = workspace / ".harness" / "skills" / "my-skill" / "v0.0.1.yaml"
        assert vf.exists()
        data = yaml.safe_load(vf.read_text())
        assert data["name"] == "my-skill"
        assert data["description"] == "desc"
        assert data["version"] == "v0.0.1"

    def test_full_skill_fields_preserved(self, workspace: Path) -> None:
        sm.save_skill_from_dict(SAMPLE_SKILL, base=workspace)
        data = sm.load_skill("code-reviewer", base=workspace)
        assert data["trigger"] == "当需要审查代码时"
        assert len(data["inputs"]) == 2
        assert data["inputs"][0]["required"] is True
        assert data["inputs"][1]["default"] == "auto"
        assert data["outputs"][0]["type"] == "array"
        assert data["assets"]["rules"] == ["output-json", "no-hallucination"]
        assert data["examples"][0]["expected_contains"] == ["缺少实现"]
        assert data["changelog"] == "首个版本"

    def test_save_from_dict_missing_name_raises(self, workspace: Path) -> None:
        with pytest.raises(ValueError, match="name"):
            sm.save_skill_from_dict({"description": "no name"}, base=workspace)


# ---------------------------------------------------------------------------
# Unit tests — load / list / delete
# ---------------------------------------------------------------------------


class TestLoadSkill:
    def test_load_current(self, workspace: Path) -> None:
        sm.save_skill("s", description="d", base=workspace)
        data = sm.load_skill("s", base=workspace)
        assert data["name"] == "s"

    def test_load_specific_version(self, workspace: Path) -> None:
        sm.save_skill("s", description="first", base=workspace)
        sm.save_skill("s", description="second", base=workspace)
        data = sm.load_skill("s", "v0.0.1", base=workspace)
        assert data["description"] == "first"

    def test_load_missing_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            sm.load_skill("no-such-skill", base=workspace)


class TestListSkills:
    def test_empty(self, workspace: Path) -> None:
        assert sm.list_skills(base=workspace) == []

    def test_lists_current_versions(self, workspace: Path) -> None:
        sm.save_skill("a", description="alpha", base=workspace)
        sm.save_skill("b", description="beta", base=workspace)
        sm.save_skill("a", description="alpha-v2", base=workspace)
        skills = sm.list_skills(base=workspace)
        names = {s["name"] for s in skills}
        assert names == {"a", "b"}
        a_data = next(s for s in skills if s["name"] == "a")
        assert a_data["version"] == "v0.0.2"


class TestListVersions:
    def test_lists_sorted(self, workspace: Path) -> None:
        sm.save_skill("x", base=workspace)
        sm.save_skill("x", base=workspace)
        sm.save_skill("x", base=workspace)
        assert sm.list_versions("x", workspace) == ["v0.0.1", "v0.0.2", "v0.0.3"]


class TestDeleteSkill:
    def test_delete_all(self, workspace: Path) -> None:
        sm.save_skill("del-me", base=workspace)
        sm.delete_skill("del-me", base=workspace)
        with pytest.raises(FileNotFoundError):
            sm.load_skill("del-me", base=workspace)

    def test_delete_specific_version(self, workspace: Path) -> None:
        sm.save_skill("ver-del", base=workspace)
        sm.save_skill("ver-del", base=workspace)
        sm.delete_skill("ver-del", "v0.0.1", base=workspace)
        assert sm.list_versions("ver-del", workspace) == ["v0.0.2"]

    def test_delete_current_repoints(self, workspace: Path) -> None:
        sm.save_skill("rcur", base=workspace)
        sm.save_skill("rcur", base=workspace)
        sm.delete_skill("rcur", "v0.0.2", base=workspace)
        assert sm.get_current_version("rcur", workspace) == "v0.0.1"

    def test_delete_missing_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            sm.delete_skill("ghost", base=workspace)


# ---------------------------------------------------------------------------
# Unit tests — _validate_skill_data
# ---------------------------------------------------------------------------


class TestValidateSkillData:
    def test_valid_minimal(self) -> None:
        errs = sm._validate_skill_data({"name": "x", "description": "d"})
        assert errs == []

    def test_missing_name(self) -> None:
        errs = sm._validate_skill_data({"description": "d"})
        assert any("name" in e for e in errs)

    def test_missing_description(self) -> None:
        errs = sm._validate_skill_data({"name": "x"})
        assert any("description" in e for e in errs)

    def test_invalid_input_entry(self) -> None:
        errs = sm._validate_skill_data(
            {"name": "x", "description": "d", "inputs": [{"name": "a"}]}
        )
        assert any("type" in e for e in errs)

    def test_invalid_output_entry(self) -> None:
        errs = sm._validate_skill_data(
            {"name": "x", "description": "d", "outputs": [{"type": "string"}]}
        )
        assert any("name" in e for e in errs)


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestSkillSaveCLI:
    def test_save_from_file(self, workspace: Path, skill_yaml: Path) -> None:
        result = runner.invoke(app, ["skill", "save", "--file", str(skill_yaml)])
        assert result.exit_code == 0, result.output
        assert "Created" in result.output
        assert "code-reviewer" in result.output
        assert "v0.0.1" in result.output

    def test_save_increments_version(self, workspace: Path, skill_yaml: Path) -> None:
        runner.invoke(app, ["skill", "save", "--file", str(skill_yaml)])
        result = runner.invoke(app, ["skill", "save", "--file", str(skill_yaml)])
        assert result.exit_code == 0, result.output
        assert "Updated" in result.output
        assert "v0.0.2" in result.output

    def test_save_missing_file(self, workspace: Path) -> None:
        result = runner.invoke(app, ["skill", "save", "--file", "/no/such/file.yaml"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "does not exist" in result.output.lower()

    def test_save_invalid_yaml(self, workspace: Path, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("{broken: yaml: ::", encoding="utf-8")
        result = runner.invoke(app, ["skill", "save", "--file", str(bad)])
        assert result.exit_code != 0

    def test_save_missing_name_field(self, workspace: Path, tmp_path: Path) -> None:
        no_name = tmp_path / "noname.yaml"
        no_name.write_text(
            yaml.dump({"description": "no name field"}), encoding="utf-8"
        )
        result = runner.invoke(app, ["skill", "save", "--file", str(no_name)])
        assert result.exit_code != 0

    def test_save_requires_init(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        p = tmp_path / "s.yaml"
        p.write_text(yaml.dump(SAMPLE_SKILL), encoding="utf-8")
        result = runner.invoke(app, ["skill", "save", "--file", str(p)])
        assert result.exit_code != 0
        assert "init" in result.output.lower()


class TestSkillShowCLI:
    def test_show_skill(self, workspace: Path, skill_yaml: Path) -> None:
        runner.invoke(app, ["skill", "save", "--file", str(skill_yaml)])
        result = runner.invoke(app, ["skill", "show", "code-reviewer"])
        assert result.exit_code == 0, result.output
        assert "code-reviewer" in result.output
        assert "审查代码" in result.output

    def test_show_specific_version(self, workspace: Path, skill_yaml: Path) -> None:
        runner.invoke(app, ["skill", "save", "--file", str(skill_yaml)])
        result = runner.invoke(app, ["skill", "show", "code-reviewer@v0.0.1"])
        assert result.exit_code == 0, result.output
        assert "v0.0.1" in result.output

    def test_show_missing(self, workspace: Path) -> None:
        result = runner.invoke(app, ["skill", "show", "ghost"])
        assert result.exit_code != 0


class TestSkillListCLI:
    def test_list_empty(self, workspace: Path) -> None:
        result = runner.invoke(app, ["skill", "list"])
        assert result.exit_code == 0, result.output
        assert "No skills" in result.output

    def test_list_shows_skill(self, workspace: Path, skill_yaml: Path) -> None:
        runner.invoke(app, ["skill", "save", "--file", str(skill_yaml)])
        result = runner.invoke(app, ["skill", "list"])
        assert result.exit_code == 0, result.output
        assert "code-reviewer" in result.output


class TestSkillDeleteCLI:
    def test_delete_skill(self, workspace: Path, skill_yaml: Path) -> None:
        runner.invoke(app, ["skill", "save", "--file", str(skill_yaml)])
        result = runner.invoke(app, ["skill", "delete", "code-reviewer", "--yes"])
        assert result.exit_code == 0, result.output
        assert "Deleted" in result.output

    def test_delete_missing(self, workspace: Path) -> None:
        result = runner.invoke(app, ["skill", "delete", "ghost", "--yes"])
        assert result.exit_code != 0
