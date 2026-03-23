"""Tests for Phase 1.4: context template asset management."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit import context as cm

runner = CliRunner()

SLOTS = [
    {"name": "code", "required": True},
    {"name": "language", "required": False, "default": "auto"},
]

TEMPLATE = "Please review the following {{ language }} code:\n```{{ language }}\n{{ code }}\n```"

SIMPLE_TEMPLATE = "Hello {{ name }}!"


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
# Unit tests — version helpers
# ---------------------------------------------------------------------------


class TestVersionHelpers:
    def test_parse_version(self) -> None:
        from harness_kit.context import _parse_version
        assert _parse_version("v1.2.3") == (1, 2, 3)
        assert _parse_version("v0.0.1") == (0, 0, 1)

    def test_bump_patch(self) -> None:
        from harness_kit.context import _bump_patch
        assert _bump_patch("v0.0.1") == "v0.0.2"
        assert _bump_patch("v1.2.9") == "v1.2.10"


# ---------------------------------------------------------------------------
# Unit tests — save_context
# ---------------------------------------------------------------------------


class TestSaveContext:
    def test_first_save_creates_v001(self, workspace: Path) -> None:
        ver, is_new = cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        assert ver == "v0.0.1"
        assert is_new is True

    def test_second_save_bumps_patch(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        ver, is_new = cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        assert ver == "v0.0.2"
        assert is_new is False

    def test_current_file_updated(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        assert cm.get_current_version("ctx", workspace) == "v0.0.2"

    def test_yaml_file_created(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, SLOTS, description="My ctx", base=workspace)
        vf = workspace / ".harness" / "contexts" / "ctx" / "v0.0.1.yaml"
        assert vf.exists()
        data = yaml.safe_load(vf.read_text())
        assert data["name"] == "ctx"
        assert data["version"] == "v0.0.1"
        assert data["description"] == "My ctx"
        assert data["slots"] == SLOTS
        assert data["template"] == TEMPLATE

    def test_tags_stored(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, tags=["review", "code"], base=workspace)
        data = cm.load_context("ctx", base=workspace)
        assert data["tags"] == ["review", "code"]

    def test_no_slots_defaults_to_empty_list(self, workspace: Path) -> None:
        cm.save_context("ctx", SIMPLE_TEMPLATE, base=workspace)
        data = cm.load_context("ctx", base=workspace)
        assert data["slots"] == []


# ---------------------------------------------------------------------------
# Unit tests — load_context
# ---------------------------------------------------------------------------


class TestLoadContext:
    def test_load_current(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        data = cm.load_context("ctx", base=workspace)
        assert data["template"] == TEMPLATE

    def test_load_specific_version(self, workspace: Path) -> None:
        cm.save_context("ctx", SIMPLE_TEMPLATE, base=workspace)
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        data = cm.load_context("ctx", "v0.0.1", workspace)
        assert data["template"] == SIMPLE_TEMPLATE

    def test_load_missing_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            cm.load_context("ghost", base=workspace)

    def test_load_missing_version_raises(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        with pytest.raises(FileNotFoundError):
            cm.load_context("ctx", "v9.9.9", workspace)


# ---------------------------------------------------------------------------
# Unit tests — list_versions
# ---------------------------------------------------------------------------


class TestListVersions:
    def test_empty_for_unknown(self, workspace: Path) -> None:
        assert cm.list_versions("nobody", workspace) == []

    def test_versions_ordered(self, workspace: Path) -> None:
        for _ in range(3):
            cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        assert cm.list_versions("ctx", workspace) == ["v0.0.1", "v0.0.2", "v0.0.3"]


# ---------------------------------------------------------------------------
# Unit tests — list_contexts
# ---------------------------------------------------------------------------


class TestListContexts:
    def test_empty(self, workspace: Path) -> None:
        assert cm.list_contexts(workspace) == []

    def test_returns_current_version(self, workspace: Path) -> None:
        cm.save_context("alpha", TEMPLATE, SLOTS, base=workspace)
        cm.save_context("beta", SIMPLE_TEMPLATE, base=workspace)
        contexts = cm.list_contexts(workspace)
        names = [c["name"] for c in contexts]
        assert "alpha" in names
        assert "beta" in names


# ---------------------------------------------------------------------------
# Unit tests — delete_context
# ---------------------------------------------------------------------------


class TestDeleteContext:
    def test_delete_all(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        cm.delete_context("ctx", base=workspace)
        assert not cm.context_dir("ctx", workspace).exists()

    def test_delete_specific_version(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        cm.delete_context("ctx", "v0.0.1", workspace)
        assert cm.list_versions("ctx", workspace) == ["v0.0.2"]

    def test_delete_current_version_updates_current(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        cm.delete_context("ctx", "v0.0.2", workspace)
        assert cm.get_current_version("ctx", workspace) == "v0.0.1"

    def test_delete_missing_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            cm.delete_context("ghost", base=workspace)

    def test_delete_missing_version_raises(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        with pytest.raises(FileNotFoundError):
            cm.delete_context("ctx", "v9.9.9", workspace)


# ---------------------------------------------------------------------------
# Unit tests — render_context
# ---------------------------------------------------------------------------


class TestRenderContext:
    def test_render_with_all_vars(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        result = cm.render_context("ctx", {"code": "print(1)", "language": "python"}, base=workspace)
        assert "python" in result
        assert "print(1)" in result

    def test_render_uses_default_for_optional(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        result = cm.render_context("ctx", {"code": "x = 1"}, base=workspace)
        # language defaults to "auto"
        assert "auto" in result
        assert "x = 1" in result

    def test_render_missing_required_raises(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        with pytest.raises(ValueError, match="Missing required slot"):
            cm.render_context("ctx", {}, base=workspace)

    def test_render_simple_template(self, workspace: Path) -> None:
        slots = [{"name": "name", "required": True}]
        cm.save_context("ctx", SIMPLE_TEMPLATE, slots, base=workspace)
        result = cm.render_context("ctx", {"name": "World"}, base=workspace)
        assert result == "Hello World!"

    def test_render_missing_context_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            cm.render_context("ghost", {"x": "1"}, base=workspace)

    def test_render_extra_vars_passed_through(self, workspace: Path) -> None:
        # Template uses an undeclared variable — Jinja2 strict would fail,
        # but if the var is provided it should succeed
        tmpl = "{{ greeting }} {{ name }}!"
        slots = [{"name": "name", "required": True}]
        cm.save_context("ctx", tmpl, slots, base=workspace)
        result = cm.render_context("ctx", {"name": "Alice", "greeting": "Hi"}, base=workspace)
        assert result == "Hi Alice!"

    def test_render_complex_list_value(self, workspace: Path) -> None:
        tmpl = "Items: {{ items }}"
        slots = [{"name": "items", "required": True}]
        cm.save_context("ctx", tmpl, slots, base=workspace)
        result = cm.render_context("ctx", {"items": ["a", "b", "c"]}, base=workspace)
        assert "a" in result
        assert "b" in result


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestContextSaveCLI:
    def test_save_with_file(self, workspace: Path) -> None:
        f = workspace / "ctx.yaml"
        f.write_text(
            "template: 'Hello {{ name }}!'\n"
            "slots:\n  - name: name\n    required: true\n"
        )
        result = runner.invoke(app, ["context", "save", "test", "--file", str(f)])
        assert result.exit_code == 0, result.output
        assert "v0.0.1" in result.output

    def test_save_increments_version(self, workspace: Path) -> None:
        f = workspace / "ctx.yaml"
        f.write_text("template: 'Hi'\n")
        runner.invoke(app, ["context", "save", "c", "--file", str(f)])
        result = runner.invoke(app, ["context", "save", "c", "--file", str(f)])
        assert "v0.0.2" in result.output

    def test_save_invalid_yaml_fails(self, workspace: Path) -> None:
        f = workspace / "ctx.yaml"
        f.write_text(": invalid: yaml: [")
        result = runner.invoke(app, ["context", "save", "bad", "--file", str(f)])
        assert result.exit_code != 0

    def test_save_no_file_fails(self, workspace: Path) -> None:
        result = runner.invoke(app, ["context", "save", "c"])
        assert result.exit_code != 0

    def test_save_not_initialized_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["context", "save", "c"])
        assert result.exit_code != 0


class TestContextRenderCLI:
    def test_render_basic(self, workspace: Path) -> None:
        cm.save_context(
            "ctx",
            SIMPLE_TEMPLATE,
            [{"name": "name", "required": True}],
            base=workspace,
        )
        result = runner.invoke(app, ["context", "render", "ctx", "--var", "name=World"])
        assert result.exit_code == 0, result.output
        assert "Hello World!" in result.output

    def test_render_multiple_vars(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        result = runner.invoke(
            app,
            ["context", "render", "ctx", "--var", "code=x=1", "--var", "language=python"],
        )
        assert result.exit_code == 0, result.output
        assert "python" in result.output

    def test_render_uses_default(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        result = runner.invoke(app, ["context", "render", "ctx", "--var", "code=x=1"])
        assert result.exit_code == 0, result.output
        assert "auto" in result.output

    def test_render_missing_required_fails(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        result = runner.invoke(app, ["context", "render", "ctx"])
        assert result.exit_code != 0
        assert "Missing required slot" in result.output

    def test_render_invalid_var_format_fails(self, workspace: Path) -> None:
        cm.save_context("ctx", SIMPLE_TEMPLATE, base=workspace)
        result = runner.invoke(app, ["context", "render", "ctx", "--var", "noequalsign"])
        assert result.exit_code != 0

    def test_render_missing_context_fails(self, workspace: Path) -> None:
        result = runner.invoke(app, ["context", "render", "ghost", "--var", "x=1"])
        assert result.exit_code != 0


class TestContextShowCLI:
    def test_show_current(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        result = runner.invoke(app, ["context", "show", "ctx"])
        assert result.exit_code == 0
        assert "ctx" in result.output
        assert "code" in result.output

    def test_show_missing_fails(self, workspace: Path) -> None:
        result = runner.invoke(app, ["context", "show", "ghost"])
        assert result.exit_code != 0


class TestContextListCLI:
    def test_list_empty(self, workspace: Path) -> None:
        result = runner.invoke(app, ["context", "list"])
        assert result.exit_code == 0
        assert "No contexts" in result.output

    def test_list_shows_contexts(self, workspace: Path) -> None:
        cm.save_context("alpha", TEMPLATE, SLOTS, description="alpha ctx", base=workspace)
        cm.save_context("beta", SIMPLE_TEMPLATE, base=workspace)
        result = runner.invoke(app, ["context", "list"])
        assert result.exit_code == 0
        assert "alpha" in result.output
        assert "beta" in result.output


class TestContextDeleteCLI:
    def test_delete_context(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        result = runner.invoke(app, ["context", "delete", "ctx", "--yes"])
        assert result.exit_code == 0
        assert not cm.context_dir("ctx", workspace).exists()

    def test_delete_specific_version(self, workspace: Path) -> None:
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        cm.save_context("ctx", TEMPLATE, SLOTS, base=workspace)
        result = runner.invoke(app, ["context", "delete", "ctx@v0.0.1", "--yes"])
        assert result.exit_code == 0
        assert cm.list_versions("ctx", workspace) == ["v0.0.2"]

    def test_delete_missing_fails(self, workspace: Path) -> None:
        result = runner.invoke(app, ["context", "delete", "ghost", "--yes"])
        assert result.exit_code != 0
