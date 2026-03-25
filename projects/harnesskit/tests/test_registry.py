"""Tests for Phase 8.8: Skills Registry (search, install, publish)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml
from typer.testing import CliRunner

from harness_kit.cli import app
from harness_kit.config import init_harness


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
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect home to tmp_path so registry writes go there."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    return home


@pytest.fixture()
def workspace_and_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    return tmp_path


def _make_skill_yaml(
    base: Path,
    name: str,
    version: str = "v0.1.0",
    description: str = "A test skill",
    trigger: str = "when needed",
    inputs: list[dict[str, Any]] | None = None,
) -> None:
    """Create a minimal skill in the .harness/ tree."""
    skill_dir = base / ".harness" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "name": name,
        "version": version,
        "description": description,
        "trigger": trigger,
        "inputs": inputs or [],
        "outputs": [],
        "assets": {},
        "changelog": "initial",
    }
    (skill_dir / f"{version}.yaml").write_text(yaml.dump(data), encoding="utf-8")
    (skill_dir / "_current").write_text(version, encoding="utf-8")


# ---------------------------------------------------------------------------
# registry.py unit tests
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_register_and_get(self, fake_home: Path) -> None:
        from harness_kit.registry import register_skill, get_registry_entry

        entry = register_skill("my-skill", "v0.1.0", "local", description="does stuff")
        assert entry["name"] == "my-skill"
        assert entry["version"] == "v0.1.0"
        assert entry["source"] == "local"

        got = get_registry_entry("my-skill")
        assert got is not None
        assert got["name"] == "my-skill"

    def test_list_registry_empty(self, fake_home: Path) -> None:
        from harness_kit.registry import list_registry

        assert list_registry() == []

    def test_list_registry_sorted(self, fake_home: Path) -> None:
        from harness_kit.registry import register_skill, list_registry

        register_skill("zebra-skill", "v1.0.0", "local")
        register_skill("alpha-skill", "v0.1.0", "local")
        names = [e["name"] for e in list_registry()]
        assert names == ["alpha-skill", "zebra-skill"]

    def test_unregister_existing(self, fake_home: Path) -> None:
        from harness_kit.registry import register_skill, unregister_skill, get_registry_entry

        register_skill("temp-skill", "v0.1.0", "local")
        assert get_registry_entry("temp-skill") is not None
        removed = unregister_skill("temp-skill")
        assert removed is True
        assert get_registry_entry("temp-skill") is None

    def test_unregister_nonexistent(self, fake_home: Path) -> None:
        from harness_kit.registry import unregister_skill

        assert unregister_skill("does-not-exist") is False

    def test_search_by_name(self, fake_home: Path) -> None:
        from harness_kit.registry import register_skill, search_registry

        register_skill("code-reviewer", "v0.1.0", "local", description="reviews code")
        register_skill("text-writer", "v0.1.0", "local", description="writes text")

        results = search_registry("code")
        assert len(results) == 1
        assert results[0]["name"] == "code-reviewer"

    def test_search_by_description(self, fake_home: Path) -> None:
        from harness_kit.registry import register_skill, search_registry

        register_skill("skill-a", "v0.1.0", "local", description="parses JSON data")
        register_skill("skill-b", "v0.1.0", "local", description="formats text")

        results = search_registry("JSON")
        assert len(results) == 1
        assert results[0]["name"] == "skill-a"

    def test_search_by_tag(self, fake_home: Path) -> None:
        from harness_kit.registry import register_skill, search_registry

        register_skill("skill-x", "v0.1.0", "local", tags=["code", "review"])
        register_skill("skill-y", "v0.1.0", "local", tags=["text"])

        results = search_registry("review")
        assert len(results) == 1
        assert results[0]["name"] == "skill-x"

    def test_search_case_insensitive(self, fake_home: Path) -> None:
        from harness_kit.registry import register_skill, search_registry

        register_skill("CodeReviewer", "v0.1.0", "local", description="Reviews Code")
        results = search_registry("codereviewer")
        assert len(results) == 1

    def test_search_no_match(self, fake_home: Path) -> None:
        from harness_kit.registry import register_skill, search_registry

        register_skill("some-skill", "v0.1.0", "local", description="does things")
        results = search_registry("xyznonexistent")
        assert results == []

    def test_registry_persists_across_loads(self, fake_home: Path) -> None:
        from harness_kit.registry import register_skill, _load_registry, _registry_file

        register_skill("persistent", "v0.2.0", "local")
        data = _load_registry()
        assert "persistent" in data
        assert data["persistent"]["version"] == "v0.2.0"

    def test_registry_file_location(self, fake_home: Path) -> None:
        from harness_kit.registry import _registry_file

        f = _registry_file()
        assert f.parent.name == ".harnesskit"
        assert f.name == "registry.json"


# ---------------------------------------------------------------------------
# skill_package.py unit tests: publish
# ---------------------------------------------------------------------------


class TestPublish:
    def test_publish_creates_hsk_file(self, workspace_and_home: Path) -> None:
        from harness_kit.skill_package import publish_skill

        _make_skill_yaml(workspace_and_home, "my-skill")
        pkg = publish_skill("my-skill", output_dir=workspace_and_home)
        assert pkg.exists()
        assert pkg.suffix == ".hsk"
        assert pkg.name == "my-skill-v0.1.0.hsk"

    def test_publish_is_valid_zip(self, workspace_and_home: Path) -> None:
        from harness_kit.skill_package import publish_skill

        _make_skill_yaml(workspace_and_home, "zip-skill")
        pkg = publish_skill("zip-skill", output_dir=workspace_and_home)
        assert zipfile.is_zipfile(pkg)

    def test_publish_contains_manifest(self, workspace_and_home: Path) -> None:
        from harness_kit.skill_package import publish_skill

        _make_skill_yaml(workspace_and_home, "manifest-skill")
        pkg = publish_skill("manifest-skill", output_dir=workspace_and_home)

        with zipfile.ZipFile(pkg, "r") as zf:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))

        assert manifest["skill_name"] == "manifest-skill"
        assert manifest["skill_version"] == "v0.1.0"
        assert "packaged_at" in manifest
        assert "files" in manifest

    def test_publish_contains_skill_yaml(self, workspace_and_home: Path) -> None:
        from harness_kit.skill_package import publish_skill

        _make_skill_yaml(workspace_and_home, "content-skill")
        pkg = publish_skill("content-skill", output_dir=workspace_and_home)

        with zipfile.ZipFile(pkg, "r") as zf:
            names = zf.namelist()
        assert any("skills/content-skill/v0.1.0.yaml" in n for n in names)

    def test_publish_unknown_skill_raises(self, workspace_and_home: Path) -> None:
        from harness_kit.skill_package import publish_skill

        with pytest.raises(FileNotFoundError):
            publish_skill("does-not-exist", output_dir=workspace_and_home)

    def test_publish_bundles_referenced_rule(self, workspace_and_home: Path) -> None:
        from harness_kit.skill_package import publish_skill

        # Create a rule
        rules_dir = workspace_and_home / ".harness" / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        (rules_dir / "no-bad-words.yaml").write_text(
            yaml.dump({"name": "no-bad-words", "type": "hard"}), encoding="utf-8"
        )

        # Create skill referencing the rule
        skill_dir = workspace_and_home / ".harness" / "skills" / "ruled-skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "name": "ruled-skill",
            "version": "v0.1.0",
            "description": "has a rule",
            "assets": {"rules": ["no-bad-words"]},
        }
        (skill_dir / "v0.1.0.yaml").write_text(yaml.dump(data), encoding="utf-8")
        (skill_dir / "_current").write_text("v0.1.0", encoding="utf-8")

        pkg = publish_skill("ruled-skill", output_dir=workspace_and_home)
        with zipfile.ZipFile(pkg, "r") as zf:
            names = zf.namelist()
        assert any("rules/no-bad-words.yaml" in n for n in names)


# ---------------------------------------------------------------------------
# skill_package.py unit tests: install from yaml
# ---------------------------------------------------------------------------


class TestInstallFromYaml:
    def test_install_yaml_creates_skill(self, workspace_and_home: Path) -> None:
        from harness_kit.skill_package import install_skill_from_path

        yaml_file = workspace_and_home / "my-skill.yaml"
        data = {
            "name": "imported-skill",
            "version": "v0.1.0",
            "description": "imported",
            "trigger": "test",
            "inputs": [],
            "outputs": [],
            "assets": {},
        }
        yaml_file.write_text(yaml.dump(data), encoding="utf-8")

        name = install_skill_from_path(yaml_file)
        assert name == "imported-skill"

        # save_skill auto-bumps; just check the skill directory was created
        skill_dir = workspace_and_home / ".harness" / "skills" / "imported-skill"
        assert skill_dir.exists()
        assert any(skill_dir.glob("v*.yaml"))

    def test_install_yaml_registers_in_registry(self, workspace_and_home: Path) -> None:
        from harness_kit.skill_package import install_skill_from_path
        from harness_kit.registry import get_registry_entry

        yaml_file = workspace_and_home / "reg-skill.yaml"
        data = {"name": "reg-skill", "version": "v0.2.0", "description": "registered skill"}
        yaml_file.write_text(yaml.dump(data), encoding="utf-8")

        install_skill_from_path(yaml_file)
        entry = get_registry_entry("reg-skill")
        assert entry is not None
        assert entry["version"] == "v0.2.0"
        assert "reg-skill.yaml" in entry["source"]

    def test_install_missing_file_raises(self, workspace_and_home: Path) -> None:
        from harness_kit.skill_package import install_skill_from_path

        with pytest.raises(FileNotFoundError):
            install_skill_from_path(workspace_and_home / "nonexistent.yaml")

    def test_install_unsupported_extension_raises(self, workspace_and_home: Path) -> None:
        from harness_kit.skill_package import install_skill_from_path

        bad_file = workspace_and_home / "skill.txt"
        bad_file.write_text("hello", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported file format"):
            install_skill_from_path(bad_file)


# ---------------------------------------------------------------------------
# skill_package.py unit tests: install from .hsk
# ---------------------------------------------------------------------------


class TestInstallFromHsk:
    def test_roundtrip_publish_then_install(self, workspace_and_home: Path) -> None:
        """Publish a skill then install the .hsk into a fresh .harness tree."""
        from harness_kit.skill_package import publish_skill, install_skill_from_path
        from harness_kit.registry import get_registry_entry

        _make_skill_yaml(workspace_and_home, "roundtrip-skill")
        pkg = publish_skill("roundtrip-skill", output_dir=workspace_and_home)
        assert pkg.exists()

        # Remove the skill from .harness to simulate fresh install
        import shutil
        shutil.rmtree(workspace_and_home / ".harness" / "skills" / "roundtrip-skill")

        name = install_skill_from_path(pkg)
        assert name == "roundtrip-skill"

        # Skill should be restored
        skill_file = workspace_and_home / ".harness" / "skills" / "roundtrip-skill" / "v0.1.0.yaml"
        assert skill_file.exists()

        entry = get_registry_entry("roundtrip-skill")
        assert entry is not None
        assert entry["version"] == "v0.1.0"

    def test_hsk_install_writes_current_marker(self, workspace_and_home: Path) -> None:
        from harness_kit.skill_package import publish_skill, install_skill_from_path

        _make_skill_yaml(workspace_and_home, "marker-skill")
        pkg = publish_skill("marker-skill", output_dir=workspace_and_home)

        import shutil
        shutil.rmtree(workspace_and_home / ".harness" / "skills" / "marker-skill")

        install_skill_from_path(pkg)
        current_file = workspace_and_home / ".harness" / "skills" / "marker-skill" / "_current"
        assert current_file.exists()
        assert current_file.read_text(encoding="utf-8").strip() == "v0.1.0"


# ---------------------------------------------------------------------------
# URL helper tests
# ---------------------------------------------------------------------------


class TestResolveRawUrl:
    def test_github_shorthand(self) -> None:
        from harness_kit.skill_package import _resolve_raw_url

        url = _resolve_raw_url("github:anthropics/harnesskit-skills/main/code-reviewer.yaml")
        assert url == "https://raw.githubusercontent.com/anthropics/harnesskit-skills/main/code-reviewer.yaml"

    def test_https_passthrough(self) -> None:
        from harness_kit.skill_package import _resolve_raw_url

        raw = "https://raw.githubusercontent.com/user/repo/main/skill.yaml"
        assert _resolve_raw_url(raw) == raw

    def test_github_too_short_raises(self) -> None:
        from harness_kit.skill_package import _resolve_raw_url

        with pytest.raises(ValueError):
            _resolve_raw_url("github:user/repo")


# ---------------------------------------------------------------------------
# CLI integration tests: skill search
# ---------------------------------------------------------------------------


class TestCliSearch:
    def test_search_empty_registry(self, workspace_and_home: Path) -> None:
        result = runner.invoke(app, ["skill", "search", "anything"])
        assert result.exit_code == 0
        assert "No registry entries" in result.output

    def test_search_finds_registered_skill(self, workspace_and_home: Path) -> None:
        from harness_kit.registry import register_skill

        register_skill("grep-skill", "v0.1.0", "local", description="greps stuff")
        result = runner.invoke(app, ["skill", "search", "grep"])
        assert result.exit_code == 0
        assert "grep-skill" in result.output

    def test_search_no_match_shows_tip(self, workspace_and_home: Path) -> None:
        result = runner.invoke(app, ["skill", "search", "zzznomatch"])
        assert result.exit_code == 0
        assert "No registry entries" in result.output


# ---------------------------------------------------------------------------
# CLI integration tests: skill install
# ---------------------------------------------------------------------------


class TestCliInstall:
    def test_install_from_yaml(self, workspace_and_home: Path) -> None:
        yaml_file = workspace_and_home / "cli-skill.yaml"
        data = {
            "name": "cli-skill",
            "version": "v0.1.0",
            "description": "installed via CLI",
            "trigger": "when",
            "inputs": [],
            "outputs": [],
            "assets": {},
        }
        yaml_file.write_text(yaml.dump(data), encoding="utf-8")

        result = runner.invoke(app, ["skill", "install", str(yaml_file)])
        assert result.exit_code == 0, result.output
        assert "cli-skill" in result.output
        assert "Installed" in result.output

    def test_install_missing_file(self, workspace_and_home: Path) -> None:
        result = runner.invoke(app, ["skill", "install", "/tmp/does_not_exist_xyz.yaml"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "File not found" in result.output

    def test_install_registers_in_registry(self, workspace_and_home: Path) -> None:
        from harness_kit.registry import get_registry_entry

        yaml_file = workspace_and_home / "reg-via-cli.yaml"
        data = {"name": "reg-via-cli", "version": "v0.3.0", "description": "test"}
        yaml_file.write_text(yaml.dump(data), encoding="utf-8")

        runner.invoke(app, ["skill", "install", str(yaml_file)])
        entry = get_registry_entry("reg-via-cli")
        assert entry is not None
        assert entry["version"] == "v0.3.0"


# ---------------------------------------------------------------------------
# CLI integration tests: skill publish
# ---------------------------------------------------------------------------


class TestCliPublish:
    def test_publish_creates_package(self, workspace_and_home: Path) -> None:
        _make_skill_yaml(workspace_and_home, "pub-skill")
        result = runner.invoke(
            app, ["skill", "publish", "pub-skill", "--output", str(workspace_and_home)]
        )
        assert result.exit_code == 0, result.output
        assert "Published" in result.output
        pkg = workspace_and_home / "pub-skill-v0.1.0.hsk"
        assert pkg.exists()

    def test_publish_unknown_skill(self, workspace_and_home: Path) -> None:
        result = runner.invoke(app, ["skill", "publish", "ghost-skill"])
        assert result.exit_code == 1

    def test_publish_output_contains_hsk_hint(self, workspace_and_home: Path) -> None:
        _make_skill_yaml(workspace_and_home, "hint-skill")
        result = runner.invoke(
            app, ["skill", "publish", "hint-skill", "--output", str(workspace_and_home)]
        )
        assert result.exit_code == 0
        assert ".hsk" in result.output
