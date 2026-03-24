"""Tests for Phase 4.5: Variable Passing System with pipe filters."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from harness_kit.blueprint_executor import (
    _apply_filter,
    interpolate_variables,
    execute_blueprint,
)
from harness_kit.config import init_harness


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


def _ctx(**kwargs) -> dict:
    """Build a minimal execution context."""
    ctx: dict = {"inputs": {}, "steps": {}}
    ctx.update(kwargs)
    return ctx


# ---------------------------------------------------------------------------
# _apply_filter unit tests
# ---------------------------------------------------------------------------


class TestApplyFilter:
    def test_truncate_long(self):
        assert _apply_filter("hello world", "truncate:5") == "hello..."

    def test_truncate_exact(self):
        assert _apply_filter("hello", "truncate:5") == "hello"

    def test_truncate_short(self):
        assert _apply_filter("hi", "truncate:10") == "hi"

    def test_truncate_zero(self):
        assert _apply_filter("hello", "truncate:0") == "..."

    def test_json_string(self):
        result = _apply_filter("hello world", "json")
        assert result == '"hello world"'

    def test_json_already_valid_object(self):
        result = _apply_filter('{"key": "value"}', "json")
        parsed = json.loads(result)
        assert parsed == {"key": "value"}

    def test_json_already_valid_array(self):
        result = _apply_filter("[1, 2, 3]", "json")
        assert json.loads(result) == [1, 2, 3]

    def test_json_number_string(self):
        # "42" parses as int, json.dumps(42) == "42"
        result = _apply_filter("42", "json")
        assert result == "42"

    def test_upper(self):
        assert _apply_filter("hello", "upper") == "HELLO"

    def test_lower(self):
        assert _apply_filter("HELLO", "lower") == "hello"

    def test_strip(self):
        assert _apply_filter("  hello  ", "strip") == "hello"

    def test_unknown_filter_unchanged(self):
        assert _apply_filter("hello", "nonexistent") == "hello"


# ---------------------------------------------------------------------------
# interpolate_variables — filter integration
# ---------------------------------------------------------------------------


class TestInterpolateVariablesFilters:
    """Phase 4.5: pipe filter syntax in {{...}} placeholders."""

    def test_truncate_filter_on_step_output(self):
        ctx = _ctx()
        ctx["steps"]["step1"] = {"output": "a" * 200, "stderr": "", "exit_code": 0, "status": "success"}
        result = interpolate_variables("{{steps.step1.output | truncate:10}}", ctx)
        assert result == "aaaaaaaaaa..."

    def test_truncate_filter_short_value(self):
        ctx = _ctx()
        ctx["steps"]["step1"] = {"output": "short", "stderr": "", "exit_code": 0, "status": "success"}
        result = interpolate_variables("{{steps.step1.output | truncate:100}}", ctx)
        assert result == "short"

    def test_json_filter_on_string(self):
        ctx = _ctx()
        ctx["steps"]["step1"] = {"output": 'hello "world"', "stderr": "", "exit_code": 0, "status": "success"}
        result = interpolate_variables("{{steps.step1.output | json}}", ctx)
        assert result == '"hello \\"world\\""'

    def test_json_filter_on_json_output(self):
        ctx = _ctx()
        ctx["steps"]["step1"] = {"output": '{"issues": []}', "stderr": "", "exit_code": 0, "status": "success"}
        result = interpolate_variables("{{steps.step1.output | json}}", ctx)
        assert json.loads(result) == {"issues": []}

    def test_upper_filter_on_input(self):
        ctx = _ctx(inputs={"lang": "python"})
        result = interpolate_variables("{{inputs.lang | upper}}", ctx)
        assert result == "PYTHON"

    def test_lower_filter_on_input(self):
        ctx = _ctx(inputs={"lang": "PYTHON"})
        result = interpolate_variables("{{inputs.lang | lower}}", ctx)
        assert result == "python"

    def test_strip_filter_on_step_output(self):
        ctx = _ctx()
        ctx["steps"]["step1"] = {"output": "  trimmed  \n", "stderr": "", "exit_code": 0, "status": "success"}
        result = interpolate_variables("{{steps.step1.output | strip}}", ctx)
        assert result == "trimmed"

    def test_chained_filters_truncate_then_upper(self):
        ctx = _ctx(inputs={"greeting": "hello world"})
        result = interpolate_variables("{{inputs.greeting | truncate:5 | upper}}", ctx)
        assert result == "HELLO..."

    def test_chained_filters_strip_then_truncate(self):
        ctx = _ctx(inputs={"msg": "  hello world  "})
        result = interpolate_variables("{{inputs.msg | strip | truncate:5}}", ctx)
        assert result == "hello..."

    def test_chained_filters_truncate_then_json(self):
        ctx = _ctx(inputs={"text": "hello world"})
        result = interpolate_variables("{{inputs.text | truncate:5 | json}}", ctx)
        # "hello..." truncated, then JSON-encoded as string
        assert result == '"hello..."'

    def test_no_filter_unchanged(self):
        ctx = _ctx(inputs={"x": "value"})
        result = interpolate_variables("{{inputs.x}}", ctx)
        assert result == "value"

    def test_unknown_filter_leaves_value_unchanged(self):
        ctx = _ctx(inputs={"x": "hello"})
        result = interpolate_variables("{{inputs.x | nonexistentfilter}}", ctx)
        assert result == "hello"

    def test_filter_on_unknown_path_leaves_placeholder(self):
        ctx = _ctx()
        result = interpolate_variables("{{steps.missing.output | truncate:5}}", ctx)
        assert result == "{{steps.missing.output | truncate:5}}"

    def test_env_var_with_filter(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR_PHASE45", "hello world from env")
        ctx = _ctx()
        result = interpolate_variables("{{env.TEST_VAR_PHASE45 | truncate:5}}", ctx)
        assert result == "hello..."

    def test_env_var_missing_with_filter(self):
        ctx = _ctx()
        # Missing env var — placeholder preserved
        result = interpolate_variables("{{env.NONEXISTENT_VAR_XYZ | upper}}", ctx)
        assert result == "{{env.NONEXISTENT_VAR_XYZ | upper}}"

    def test_mixed_template_with_filter(self):
        ctx = _ctx(inputs={"lang": "python"})
        ctx["steps"]["lint"] = {"output": "no issues found", "stderr": "", "exit_code": 0, "status": "success"}
        result = interpolate_variables(
            "Language: {{inputs.lang | upper}}, result: {{steps.lint.output | truncate:10}}",
            ctx,
        )
        # "no issues found"[:10] == "no issues " (with trailing space)
        assert result == "Language: PYTHON, result: no issues ..."

    def test_exit_code_with_json_filter(self):
        ctx = _ctx()
        ctx["steps"]["step1"] = {"output": "", "stderr": "", "exit_code": 0, "status": "success"}
        result = interpolate_variables("{{steps.step1.exit_code | json}}", ctx)
        assert result == "0"  # json.dumps(0) == "0"


# ---------------------------------------------------------------------------
# End-to-end: execute_blueprint with filter interpolation
# ---------------------------------------------------------------------------


class TestExecuteBlueprintWithFilters:
    """Integration tests — filters applied within a real blueprint execution."""

    def test_deterministic_step_uses_truncate_filter(self, tmp_base: Path):
        """The second step uses {{steps.gen.output | truncate:5}} in its run command."""
        bp = {
            "name": "filter-pipeline",
            "description": "Test pipe filters in blueprint execution",
            "inputs": [],
            "steps": [
                {
                    "id": "gen",
                    "type": "deterministic",
                    "name": "Generate long output",
                    "run": "echo 'hello world from blueprint'",
                    "on_fail": "stop",
                    "timeout": 10,
                },
                {
                    "id": "use_truncated",
                    "type": "deterministic",
                    "name": "Use truncated output",
                    "run": "echo '{{steps.gen.output | strip | truncate:5}}'",
                    "on_fail": "stop",
                    "timeout": 10,
                },
            ],
            "outputs": {
                "raw": "{{steps.gen.output | strip}}",
                "short": "{{steps.gen.output | strip | truncate:5}}",
            },
        }
        result = execute_blueprint(bp, {}, base=tmp_base)
        assert result.status == "success"
        assert result.outputs["raw"] == "hello world from blueprint"
        assert result.outputs["short"] == "hello..."

    def test_output_json_filter(self, tmp_base: Path):
        """The outputs section uses | json filter."""
        bp = {
            "name": "json-filter-pipeline",
            "description": "JSON filter test",
            "inputs": [{"name": "greeting", "required": True}],
            "steps": [
                {
                    "id": "echo",
                    "type": "deterministic",
                    "name": "Echo greeting",
                    "run": "echo '{{inputs.greeting}}'",
                    "on_fail": "stop",
                    "timeout": 10,
                },
            ],
            "outputs": {
                "result_json": "{{steps.echo.output | strip | json}}",
            },
        }
        result = execute_blueprint(bp, {"greeting": "hello"}, base=tmp_base)
        assert result.status == "success"
        # JSON-encoded value should be a valid JSON string
        json_val = result.outputs["result_json"]
        parsed = json.loads(json_val)
        assert parsed == "hello"

    def test_input_filter_in_step_run(self, tmp_base: Path):
        """Input variable filtered to upper-case in the run command."""
        bp = {
            "name": "input-filter-pipeline",
            "description": "Input filter test",
            "inputs": [{"name": "lang", "required": True}],
            "steps": [
                {
                    "id": "show",
                    "type": "deterministic",
                    "name": "Show language",
                    "run": "echo '{{inputs.lang | upper}}'",
                    "on_fail": "stop",
                    "timeout": 10,
                },
            ],
            "outputs": {"result": "{{steps.show.output | strip}}"},
        }
        result = execute_blueprint(bp, {"lang": "python"}, base=tmp_base)
        assert result.status == "success"
        assert result.outputs["result"] == "PYTHON"

    def test_dry_run_shows_interpolated_filters(self, tmp_base: Path):
        """dry_run renders the command with filters applied."""
        bp = {
            "name": "dry-run-filter",
            "description": "Dry run filter test",
            "inputs": [{"name": "msg", "required": True}],
            "steps": [
                {
                    "id": "process",
                    "type": "deterministic",
                    "name": "Process message",
                    "run": "echo '{{inputs.msg | truncate:3}}'",
                    "on_fail": "stop",
                    "timeout": 10,
                },
            ],
            "outputs": {},
        }
        result = execute_blueprint(bp, {"msg": "hello world"}, dry_run=True, base=tmp_base)
        assert result.status == "dry_run"
        step_result = result.steps[0]
        # dry_run output should show the rendered (filtered) command
        assert "hel..." in step_result.output
