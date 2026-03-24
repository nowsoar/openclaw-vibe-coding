"""Tests for Phase 2.5: Skill advanced version management (tag, clone, deps)."""

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
# Sample skill data
# ---------------------------------------------------------------------------

SAMPLE_SKILL: dict = {
    "name": "code-reviewer",
    "description": "审查代码，输出问题列表",
    "trigger": "当需要审查代码时",
    "inputs": [
        {"name": "code", "type": "string", "required": True},
        {"name": "language", "type": "string", "default": "auto"},
    ],
    "outputs": [{"name": "issues", "type": "array"}],
    "assets": {
        "prompts": {"system": "code-reviewer-system@v0.1.0"},
        "rules": ["output-json", "no-hallucination"],
        "context": "code-review-ctx@v0.0.1",
        "schemas": ["read-file@v0.0.1"],
    },
    "changelog": "首个版本",
}


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Initialised .harness workspace in tmp_path, CWD set to it."""
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


@pytest.fixture()
def workspace_with_skill(workspace: Path) -> tuple[Path, str]:
    """Returns (workspace, v0.0.1) with one saved skill."""
    version, _ = sm.save_skill_from_dict(SAMPLE_SKILL, base=workspace)
    return workspace, version


# ---------------------------------------------------------------------------
# tag_skill — unit tests
# ---------------------------------------------------------------------------


class TestTagSkill:
    def test_tag_current_version(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, version = workspace_with_skill
        tagged = sm.tag_skill("code-reviewer", "production", base=base)
        assert tagged == version

    def test_tag_file_created(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, version = workspace_with_skill
        sm.tag_skill("code-reviewer", "production", base=base)
        tf = sm.skill_dir("code-reviewer", base) / "_tag_production"
        assert tf.exists()
        assert tf.read_text(encoding="utf-8").strip() == version

    def test_tag_specific_version(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, v1 = workspace_with_skill
        sm.save_skill_from_dict(SAMPLE_SKILL, base=base)  # creates v0.0.2
        tagged = sm.tag_skill("code-reviewer", "stable", v1, base=base)
        assert tagged == v1

    def test_tag_missing_skill_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            sm.tag_skill("nonexistent", "production", base=workspace)

    def test_tag_missing_version_raises(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, _ = workspace_with_skill
        with pytest.raises(FileNotFoundError):
            sm.tag_skill("code-reviewer", "bad", "v9.9.9", base=base)


# ---------------------------------------------------------------------------
# list_tags — unit tests
# ---------------------------------------------------------------------------


class TestListTags:
    def test_empty_tags(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, _ = workspace_with_skill
        assert sm.list_tags("code-reviewer", base=base) == {}

    def test_lists_created_tags(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, version = workspace_with_skill
        sm.tag_skill("code-reviewer", "production", base=base)
        sm.tag_skill("code-reviewer", "staging", base=base)
        tags = sm.list_tags("code-reviewer", base=base)
        assert tags == {"production": version, "staging": version}

    def test_missing_skill_returns_empty(self, workspace: Path) -> None:
        assert sm.list_tags("ghost", base=workspace) == {}


# ---------------------------------------------------------------------------
# load_skill with tag alias
# ---------------------------------------------------------------------------


class TestLoadSkillWithTag:
    def test_load_via_tag(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, version = workspace_with_skill
        sm.tag_skill("code-reviewer", "production", base=base)
        data = sm.load_skill("code-reviewer", "production", base=base)
        assert data["version"] == version

    def test_load_unknown_tag_raises(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, _ = workspace_with_skill
        with pytest.raises(FileNotFoundError, match="no such tag"):
            sm.load_skill("code-reviewer", "nonexistenttag", base=base)

    def test_tag_points_to_old_version(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, v1 = workspace_with_skill
        sm.tag_skill("code-reviewer", "stable", v1, base=base)
        sm.save_skill_from_dict(SAMPLE_SKILL, base=base)  # creates v0.0.2
        data = sm.load_skill("code-reviewer", "stable", base=base)
        assert data["version"] == v1


# ---------------------------------------------------------------------------
# clone_skill — unit tests
# ---------------------------------------------------------------------------


class TestCloneSkill:
    def test_clone_creates_new_skill(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, _ = workspace_with_skill
        sm.clone_skill("code-reviewer", "code-reviewer-v2", base=base)
        assert sm.skill_dir("code-reviewer-v2", base).exists()

    def test_clone_resets_version(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, _ = workspace_with_skill
        sm.save_skill_from_dict(SAMPLE_SKILL, base=base)
        sm.save_skill_from_dict(SAMPLE_SKILL, base=base)
        sm.clone_skill("code-reviewer", "code-reviewer-fork", base=base)
        data = sm.load_skill("code-reviewer-fork", base=base)
        assert data["version"] == "v0.0.1"

    def test_clone_sets_new_name(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, _ = workspace_with_skill
        sm.clone_skill("code-reviewer", "new-reviewer", base=base)
        data = sm.load_skill("new-reviewer", base=base)
        assert data["name"] == "new-reviewer"

    def test_clone_copies_assets(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, _ = workspace_with_skill
        sm.clone_skill("code-reviewer", "new-reviewer", base=base)
        data = sm.load_skill("new-reviewer", base=base)
        assert data["assets"]["rules"] == ["output-json", "no-hallucination"]

    def test_clone_current_file_is_v001(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, _ = workspace_with_skill
        sm.clone_skill("code-reviewer", "cloned", base=base)
        assert sm.get_current_version("cloned", base=base) == "v0.0.1"

    def test_clone_source_missing_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            sm.clone_skill("ghost", "new-ghost", base=workspace)

    def test_clone_target_exists_raises(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, _ = workspace_with_skill
        sm.save_skill_from_dict({**SAMPLE_SKILL, "name": "target-skill"}, base=base)
        with pytest.raises(FileExistsError, match="already exists"):
            sm.clone_skill("code-reviewer", "target-skill", base=base)

    def test_clone_returns_v001(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, _ = workspace_with_skill
        result = sm.clone_skill("code-reviewer", "new-rev", base=base)
        assert result == "v0.0.1"


# ---------------------------------------------------------------------------
# get_skill_deps — unit tests
# ---------------------------------------------------------------------------


class TestGetSkillDeps:
    def test_all_deps_listed(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, _ = workspace_with_skill
        deps = sm.get_skill_deps("code-reviewer", base=base)
        assert "code-reviewer-system@v0.1.0" in deps["prompts"]
        assert "output-json" in deps["rules"]
        assert "no-hallucination" in deps["rules"]
        assert "code-review-ctx@v0.0.1" in deps["context"]
        assert "read-file@v0.0.1" in deps["schemas"]

    def test_no_assets_skill(self, workspace: Path) -> None:
        sm.save_skill_from_dict(
            {
                "name": "simple",
                "description": "simple skill",
                "inputs": [{"name": "x", "type": "string"}],
                "outputs": [{"name": "y", "type": "string"}],
            },
            base=workspace,
        )
        deps = sm.get_skill_deps("simple", base=workspace)
        assert deps == {"prompts": [], "schemas": [], "rules": [], "context": []}

    def test_missing_skill_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            sm.get_skill_deps("ghost", base=workspace)

    def test_total_count(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, _ = workspace_with_skill
        deps = sm.get_skill_deps("code-reviewer", base=base)
        total = sum(len(v) for v in deps.values())
        # 1 prompt + 2 rules + 1 context + 1 schema = 5
        assert total == 5


# ---------------------------------------------------------------------------
# CLI: skill tag
# ---------------------------------------------------------------------------


class TestSkillTagCLI:
    def test_tag_success(self, workspace_with_skill: tuple[Path, str]) -> None:
        _, version = workspace_with_skill
        result = runner.invoke(app, ["skill", "tag", "code-reviewer", "--name", "production"])
        assert result.exit_code == 0, result.output
        assert "Tagged" in result.output
        assert "production" in result.output

    def test_tag_output_includes_version(self, workspace_with_skill: tuple[Path, str]) -> None:
        _, version = workspace_with_skill
        result = runner.invoke(app, ["skill", "tag", "code-reviewer", "--name", "prod"])
        assert version in result.output

    def test_tag_missing_skill(self, workspace: Path) -> None:
        result = runner.invoke(app, ["skill", "tag", "ghost", "--name", "production"])
        assert result.exit_code != 0

    def test_show_tagged_version(self, workspace_with_skill: tuple[Path, str]) -> None:
        runner.invoke(app, ["skill", "tag", "code-reviewer", "--name", "production"])
        result = runner.invoke(app, ["skill", "show", "code-reviewer@production"])
        assert result.exit_code == 0, result.output
        assert "code-reviewer" in result.output

    def test_tag_specific_version_flag(self, workspace_with_skill: tuple[Path, str]) -> None:
        _, v1 = workspace_with_skill
        sm.save_skill_from_dict(SAMPLE_SKILL)  # creates v0.0.2 in cwd
        result = runner.invoke(
            app, ["skill", "tag", "code-reviewer", "--name", "old", "--version", v1]
        )
        assert result.exit_code == 0, result.output
        assert v1 in result.output

    def test_requires_init(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["skill", "tag", "code-reviewer", "--name", "prod"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# CLI: skill clone
# ---------------------------------------------------------------------------


class TestSkillCloneCLI:
    def test_clone_success(self, workspace_with_skill: tuple[Path, str]) -> None:
        result = runner.invoke(app, ["skill", "clone", "code-reviewer", "code-reviewer-v2"])
        assert result.exit_code == 0, result.output
        assert "Cloned" in result.output
        assert "code-reviewer-v2" in result.output
        assert "v0.0.1" in result.output

    def test_clone_missing_source(self, workspace: Path) -> None:
        result = runner.invoke(app, ["skill", "clone", "ghost", "new-ghost"])
        assert result.exit_code != 0
        assert "✗" in result.output

    def test_clone_target_exists(self, workspace_with_skill: tuple[Path, str]) -> None:
        base, _ = workspace_with_skill
        sm.save_skill_from_dict({**SAMPLE_SKILL, "name": "target"}, base=base)
        result = runner.invoke(app, ["skill", "clone", "code-reviewer", "target"])
        assert result.exit_code != 0

    def test_clone_requires_init(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["skill", "clone", "a", "b"])
        assert result.exit_code != 0

    def test_cloned_skill_visible_in_list(self, workspace_with_skill: tuple[Path, str]) -> None:
        runner.invoke(app, ["skill", "clone", "code-reviewer", "forked"])
        result = runner.invoke(app, ["skill", "list"])
        assert "forked" in result.output


# ---------------------------------------------------------------------------
# CLI: skill deps
# ---------------------------------------------------------------------------


class TestSkillDepsCLI:
    def test_deps_lists_all(self, workspace_with_skill: tuple[Path, str]) -> None:
        result = runner.invoke(app, ["skill", "deps", "code-reviewer"])
        assert result.exit_code == 0, result.output
        assert "code-reviewer-system@v0.1.0" in result.output
        assert "output-json" in result.output
        assert "no-hallucination" in result.output
        assert "code-review-ctx@v0.0.1" in result.output
        assert "read-file@v0.0.1" in result.output

    def test_deps_no_assets(self, workspace: Path) -> None:
        sm.save_skill_from_dict(
            {
                "name": "bare",
                "description": "bare skill",
                "inputs": [{"name": "x", "type": "string"}],
                "outputs": [{"name": "y", "type": "string"}],
            },
            base=workspace,
        )
        result = runner.invoke(app, ["skill", "deps", "bare"])
        assert result.exit_code == 0, result.output
        assert "no asset dependencies" in result.output

    def test_deps_missing_skill(self, workspace: Path) -> None:
        result = runner.invoke(app, ["skill", "deps", "ghost"])
        assert result.exit_code != 0

    def test_deps_requires_init(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["skill", "deps", "code-reviewer"])
        assert result.exit_code != 0

    def test_deps_shows_total_count(self, workspace_with_skill: tuple[Path, str]) -> None:
        result = runner.invoke(app, ["skill", "deps", "code-reviewer"])
        assert result.exit_code == 0, result.output
        # 1 prompt + 2 rules + 1 context + 1 schema = 5
        assert "5" in result.output
