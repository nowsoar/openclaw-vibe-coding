"""Phase 1.7 — End-to-end integration tests.

Covers the full user workflow:
  init → save prompt → save schema → create context → add rule → doctor
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness_kit.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fresh temp directory with no .harness/ yet."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def invoke(*args: str) -> tuple[int, str]:
    """Run CLI command and return (exit_code, output)."""
    result = runner.invoke(app, list(args))
    return result.exit_code, result.output


# ---------------------------------------------------------------------------
# Test: full happy-path workflow
# ---------------------------------------------------------------------------


class TestFullWorkflow:
    """init → prompt save → schema save → context save → rule add → doctor."""

    def test_init_creates_harness_dir(self, workspace: Path) -> None:
        code, out = invoke("init")
        assert code == 0
        assert "Initialized HarnessKit project" in out
        assert (workspace / ".harness").is_dir()
        assert (workspace / ".harness" / "config.yaml").is_file()
        for sub in ("prompts", "schemas", "contexts", "rules", "skills"):
            assert (workspace / ".harness" / sub).is_dir(), f"Missing subdir: {sub}"

    def test_init_twice_is_idempotent(self, workspace: Path) -> None:
        invoke("init")
        code, out = invoke("init")
        assert code == 0
        assert "Already initialized" in out

    def test_prompt_save_and_show(self, workspace: Path) -> None:
        invoke("init")
        code, out = invoke(
            "prompt", "save", "code-reviewer",
            "--content", "You are a senior {{language}} engineer.",
            "--description", "Code review prompt",
            "--tags", "code,review",
            "--changelog", "Initial version",
        )
        assert code == 0
        assert "Created" in out
        assert "code-reviewer" in out
        assert "v0.0.1" in out

        code, out = invoke("prompt", "show", "code-reviewer")
        assert code == 0
        assert "code-reviewer" in out
        assert "Code review prompt" in out
        assert "You are a senior {{language}} engineer." in out

    def test_prompt_list(self, workspace: Path) -> None:
        invoke("init")
        invoke("prompt", "save", "p1", "--content", "First prompt")
        invoke("prompt", "save", "p2", "--content", "Second prompt")
        code, out = invoke("prompt", "list")
        assert code == 0
        assert "p1" in out
        assert "p2" in out

    def test_prompt_version_increments(self, workspace: Path) -> None:
        invoke("init")
        invoke("prompt", "save", "versioned", "--content", "v1 content")
        code, out = invoke("prompt", "save", "versioned", "--content", "v2 content")
        assert code == 0
        assert "v0.0.2" in out

    def test_prompt_history(self, workspace: Path) -> None:
        invoke("init")
        invoke("prompt", "save", "hist-test", "--content", "rev 1")
        invoke("prompt", "save", "hist-test", "--content", "rev 2")
        code, out = invoke("prompt", "history", "hist-test")
        assert code == 0
        assert "v0.0.1" in out
        assert "v0.0.2" in out
        assert "current" in out

    def test_prompt_diff(self, workspace: Path) -> None:
        invoke("init")
        invoke("prompt", "save", "diff-me", "--content", "alpha")
        invoke("prompt", "save", "diff-me", "--content", "beta")
        code, out = invoke("prompt", "diff", "diff-me@v0.0.1", "diff-me@v0.0.2")
        assert code == 0
        # Should contain diff markers
        assert "+" in out or "-" in out or "alpha" in out or "beta" in out

    def test_schema_save_and_show(self, workspace: Path) -> None:
        invoke("init")
        schema_json = json.dumps({
            "description": "Read a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"}
                },
                "required": ["path"],
            },
        })
        schema_path = workspace / "read_file.json"
        schema_path.write_text(schema_json, encoding="utf-8")

        code, out = invoke("schema", "save", "read-file", "--file", str(schema_path))
        assert code == 0
        assert "read-file" in out

        code, out = invoke("schema", "show", "read-file")
        assert code == 0
        assert "read-file" in out
        assert "path" in out

    def test_schema_validate(self, workspace: Path) -> None:
        invoke("init")
        schema_path = workspace / "s.json"
        schema_path.write_text(json.dumps({
            "type": "object",
            "properties": {"x": {"type": "integer"}},
        }), encoding="utf-8")
        invoke("schema", "save", "valid-schema", "--file", str(schema_path))
        code, out = invoke("schema", "validate", "valid-schema")
        assert code == 0
        assert "valid" in out.lower()

    def test_context_save_and_render(self, workspace: Path) -> None:
        invoke("init")
        ctx_yaml = workspace / "ctx.yaml"
        ctx_yaml.write_text(
            "description: Review context\n"
            "slots:\n"
            "  - name: language\n"
            "    required: true\n"
            "  - name: code\n"
            "    required: true\n"
            "template: |\n"
            "  Review the following {{language}} code:\n"
            "  {{code}}\n",
            encoding="utf-8",
        )
        code, out = invoke("context", "save", "review-ctx", "--file", str(ctx_yaml))
        assert code == 0
        assert "review-ctx" in out

        code, out = invoke(
            "context", "render", "review-ctx",
            "--var", "language=Python",
            "--var", "code=def foo(): pass",
        )
        assert code == 0
        assert "Python" in out
        assert "def foo(): pass" in out

    def test_context_list(self, workspace: Path) -> None:
        invoke("init")
        ctx_yaml = workspace / "c.yaml"
        ctx_yaml.write_text(
            "slots: []\ntemplate: hello\n", encoding="utf-8"
        )
        invoke("context", "save", "my-ctx", "--file", str(ctx_yaml))
        code, out = invoke("context", "list")
        assert code == 0
        assert "my-ctx" in out

    def test_rule_add_and_show(self, workspace: Path) -> None:
        invoke("init")
        code, out = invoke(
            "rule", "add", "no-hallucination",
            "--type", "hard",
            "--pattern", r"(根据我所知|我猜测)",
            "--description", "No guessing",
            "--fix-hint", "Remove speculation",
        )
        assert code == 0
        assert "Created" in out or "Updated" in out
        assert "no-hallucination" in out

        code, out = invoke("rule", "show", "no-hallucination")
        assert code == 0
        assert "no-hallucination" in out
        assert "hard" in out

    def test_rule_test_triggered(self, workspace: Path) -> None:
        invoke("init")
        invoke(
            "rule", "add", "no-guess",
            "--type", "hard",
            "--pattern", "我猜测",
        )
        code, out = invoke("rule", "test", "no-guess", "--input", "我猜测这是对的")
        assert code == 0
        assert "TRIGGERED" in out

    def test_rule_test_not_triggered(self, workspace: Path) -> None:
        invoke("init")
        invoke(
            "rule", "add", "no-guess",
            "--type", "hard",
            "--pattern", "我猜测",
        )
        code, out = invoke("rule", "test", "no-guess", "--input", "这是确认的事实")
        assert code == 0
        assert "PASSED" in out

    def test_rule_list(self, workspace: Path) -> None:
        invoke("init")
        invoke("rule", "add", "rule-a", "--type", "soft", "--pattern", "foo")
        invoke("rule", "add", "rule-b", "--type", "hard", "--pattern", "bar")
        code, out = invoke("rule", "list")
        assert code == 0
        assert "rule-a" in out
        assert "rule-b" in out

    def test_doctor_clean_workspace(self, workspace: Path) -> None:
        invoke("init")
        code, out = invoke("doctor")
        assert code == 0
        assert "No circular references" in out
        assert "Summary" in out

    def test_doctor_after_assets_created(self, workspace: Path) -> None:
        """Doctor should pass on a workspace with valid assets."""
        invoke("init")

        # Create prompt
        invoke("prompt", "save", "sys-prompt", "--content", "You are an assistant.")

        # Create schema
        schema_path = workspace / "schema.json"
        schema_path.write_text(json.dumps({
            "type": "object",
            "properties": {"q": {"type": "string"}},
        }), encoding="utf-8")
        invoke("schema", "save", "query-schema", "--file", str(schema_path))

        # Create context
        ctx_path = workspace / "ctx.yaml"
        ctx_path.write_text(
            "slots:\n  - name: q\n    required: true\ntemplate: 'Query: {{q}}'\n",
            encoding="utf-8",
        )
        invoke("context", "save", "query-ctx", "--file", str(ctx_path))

        # Add rule
        invoke("rule", "add", "no-guess", "--type", "hard", "--pattern", "I guess")

        # Doctor should not report broken references or cycles
        code, out = invoke("doctor")
        assert code == 0
        assert "No circular references" in out
        assert "Summary" in out


# ---------------------------------------------------------------------------
# Test: error paths
# ---------------------------------------------------------------------------


class TestErrorPaths:
    """Commands fail clearly when workspace is not initialised or asset missing."""

    def test_prompt_save_without_init(self, workspace: Path) -> None:
        code, out = invoke("prompt", "save", "x", "--content", "y")
        assert code != 0
        assert "init" in out.lower() or "not initialized" in out.lower()

    def test_schema_save_without_init(self, workspace: Path) -> None:
        schema_path = workspace / "s.json"
        schema_path.write_text('{"type": "object"}', encoding="utf-8")
        code, out = invoke("schema", "save", "x", "--file", str(schema_path))
        assert code != 0

    def test_context_save_without_init(self, workspace: Path) -> None:
        ctx_path = workspace / "c.yaml"
        ctx_path.write_text("slots: []\ntemplate: hi\n", encoding="utf-8")
        code, out = invoke("context", "save", "x", "--file", str(ctx_path))
        assert code != 0

    def test_rule_add_without_init(self, workspace: Path) -> None:
        code, out = invoke("rule", "add", "x", "--pattern", "y")
        assert code != 0

    def test_prompt_show_missing(self, workspace: Path) -> None:
        invoke("init")
        code, out = invoke("prompt", "show", "nonexistent")
        assert code != 0
        assert "✗" in out or "not found" in out.lower() or "nonexistent" in out.lower()

    def test_schema_show_missing(self, workspace: Path) -> None:
        invoke("init")
        code, out = invoke("schema", "show", "nonexistent")
        assert code != 0

    def test_context_render_missing_required_slot(self, workspace: Path) -> None:
        invoke("init")
        ctx_path = workspace / "ctx.yaml"
        ctx_path.write_text(
            "slots:\n  - name: q\n    required: true\ntemplate: '{{q}}'\n",
            encoding="utf-8",
        )
        invoke("context", "save", "ctx-req", "--file", str(ctx_path))
        code, out = invoke("context", "render", "ctx-req")
        assert code != 0

    def test_rule_test_missing_rule(self, workspace: Path) -> None:
        invoke("init")
        code, out = invoke("rule", "test", "ghost-rule", "--input", "text")
        assert code != 0

    def test_doctor_without_init(self, workspace: Path) -> None:
        code, out = invoke("doctor")
        assert code != 0
        assert "init" in out.lower() or "not initialized" in out.lower()


# ---------------------------------------------------------------------------
# Test: delete operations
# ---------------------------------------------------------------------------


class TestDeleteOperations:
    """Ensure delete commands work correctly."""

    def test_prompt_delete_all_versions(self, workspace: Path) -> None:
        invoke("init")
        invoke("prompt", "save", "del-me", "--content", "v1")
        invoke("prompt", "save", "del-me", "--content", "v2")
        code, out = invoke("prompt", "delete", "del-me", "--yes")
        assert code == 0
        assert "Deleted" in out
        # Confirm it is gone
        code2, out2 = invoke("prompt", "show", "del-me")
        assert code2 != 0

    def test_prompt_delete_specific_version(self, workspace: Path) -> None:
        invoke("init")
        invoke("prompt", "save", "keep-me", "--content", "v1")
        invoke("prompt", "save", "keep-me", "--content", "v2")
        code, out = invoke("prompt", "delete", "keep-me@v0.0.1", "--yes")
        assert code == 0
        # v0.0.2 should still exist
        code2, _ = invoke("prompt", "show", "keep-me@v0.0.2")
        assert code2 == 0

    def test_schema_delete(self, workspace: Path) -> None:
        invoke("init")
        sp = workspace / "s.json"
        sp.write_text('{"type": "object"}', encoding="utf-8")
        invoke("schema", "save", "del-schema", "--file", str(sp))
        code, out = invoke("schema", "delete", "del-schema", "--yes")
        assert code == 0
        assert "Deleted" in out

    def test_context_delete(self, workspace: Path) -> None:
        invoke("init")
        cp = workspace / "c.yaml"
        cp.write_text("slots: []\ntemplate: hi\n", encoding="utf-8")
        invoke("context", "save", "del-ctx", "--file", str(cp))
        code, out = invoke("context", "delete", "del-ctx", "--yes")
        assert code == 0
        assert "Deleted" in out

    def test_rule_delete(self, workspace: Path) -> None:
        invoke("init")
        invoke("rule", "add", "del-rule", "--type", "soft", "--pattern", "x")
        code, out = invoke("rule", "delete", "del-rule", "--yes")
        assert code == 0
        assert "Deleted" in out
        code2, _ = invoke("rule", "show", "del-rule")
        assert code2 != 0
