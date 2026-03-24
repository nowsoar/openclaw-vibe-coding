"""Tests for Phase 5.1: Test Suite data model and storage."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit import eval as em

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


MINIMAL_SUITE: dict = {
    "name": "code-review-suite",
    "description": "代码审查测试集",
    "cases": [
        {
            "id": "detect-bug",
            "name": "发现除零错误",
            "inputs": {"code": "def divide(a, b): return a/b", "language": "python"},
            "assertions": [
                {"type": "contains", "path": "$.issues[*].type", "value": "ZeroDivisionError"},
                {"type": "regex", "path": "$.summary", "pattern": "异常处理|error handling"},
            ],
        }
    ],
}

MULTI_CASE_SUITE: dict = {
    "name": "multi-case",
    "description": "Multiple assertion types test",
    "cases": [
        {
            "id": "case-contains",
            "name": "Contains assertion",
            "inputs": {"code": "def foo(): pass"},
            "assertions": [
                {"type": "contains", "path": "$.issues[*].message", "value": "缺少实现"},
            ],
        },
        {
            "id": "case-regex",
            "name": "Regex assertion",
            "inputs": {"text": "hello world"},
            "assertions": [
                {"type": "regex", "path": "$.output", "pattern": "hello"},
            ],
        },
        {
            "id": "case-json-schema",
            "name": "JSON Schema assertion",
            "inputs": {},
            "assertions": [
                {
                    "type": "json_schema",
                    "path": "$.result",
                    "schema": {"type": "object", "properties": {"issues": {"type": "array"}}},
                },
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Unit tests — _validate_suite_data
# ---------------------------------------------------------------------------


class TestValidateSuiteData:
    def test_valid_minimal(self) -> None:
        errors = em._validate_suite_data(MINIMAL_SUITE)
        assert errors == []

    def test_missing_name(self) -> None:
        data = {**MINIMAL_SUITE, "name": ""}
        errors = em._validate_suite_data(data)
        assert any("'name' is required" in e for e in errors)

    def test_missing_description(self) -> None:
        data = {**MINIMAL_SUITE, "description": ""}
        errors = em._validate_suite_data(data)
        assert any("'description' is required" in e for e in errors)

    def test_missing_cases(self) -> None:
        data = {"name": "x", "description": "y"}
        errors = em._validate_suite_data(data)
        assert any("'cases' is required" in e for e in errors)

    def test_empty_cases(self) -> None:
        data = {**MINIMAL_SUITE, "cases": []}
        errors = em._validate_suite_data(data)
        assert any("must not be empty" in e for e in errors)

    def test_duplicate_case_ids(self) -> None:
        case = MINIMAL_SUITE["cases"][0]
        data = {**MINIMAL_SUITE, "cases": [case, case]}
        errors = em._validate_suite_data(data)
        assert any("Duplicate case id" in e for e in errors)

    def test_case_missing_id(self) -> None:
        data = {
            **MINIMAL_SUITE,
            "cases": [{"name": "x", "assertions": [{"type": "contains", "path": "$.a", "value": "b"}]}],
        }
        errors = em._validate_suite_data(data)
        assert any("'id' is required" in e for e in errors)

    def test_case_missing_assertions(self) -> None:
        data = {**MINIMAL_SUITE, "cases": [{"id": "x", "name": "x"}]}
        errors = em._validate_suite_data(data)
        assert any("'assertions' is required" in e for e in errors)

    def test_invalid_assertion_type(self) -> None:
        data = {
            **MINIMAL_SUITE,
            "cases": [{"id": "x", "name": "x", "assertions": [{"type": "unknown"}]}],
        }
        errors = em._validate_suite_data(data)
        assert any("unsupported type" in e for e in errors)

    def test_contains_missing_path(self) -> None:
        data = {
            **MINIMAL_SUITE,
            "cases": [{"id": "x", "name": "x", "assertions": [{"type": "contains", "value": "v"}]}],
        }
        errors = em._validate_suite_data(data)
        assert any("'path' is required" in e for e in errors)

    def test_contains_missing_value(self) -> None:
        data = {
            **MINIMAL_SUITE,
            "cases": [{"id": "x", "name": "x", "assertions": [{"type": "contains", "path": "$.x"}]}],
        }
        errors = em._validate_suite_data(data)
        assert any("'value' is required" in e for e in errors)

    def test_regex_invalid_pattern(self) -> None:
        data = {
            **MINIMAL_SUITE,
            "cases": [
                {"id": "x", "name": "x", "assertions": [{"type": "regex", "path": "$.x", "pattern": "[invalid"}]}
            ],
        }
        errors = em._validate_suite_data(data)
        assert any("invalid pattern" in e for e in errors)

    def test_json_schema_missing_schema(self) -> None:
        data = {
            **MINIMAL_SUITE,
            "cases": [{"id": "x", "name": "x", "assertions": [{"type": "json_schema", "path": "$.x"}]}],
        }
        errors = em._validate_suite_data(data)
        assert any("'schema' is required" in e for e in errors)

    def test_custom_missing_function(self) -> None:
        data = {
            **MINIMAL_SUITE,
            "cases": [{"id": "x", "name": "x", "assertions": [{"type": "custom"}]}],
        }
        errors = em._validate_suite_data(data)
        assert any("'function' is required" in e for e in errors)

    def test_all_assertion_types_valid(self) -> None:
        errors = em._validate_suite_data(MULTI_CASE_SUITE)
        assert errors == []


# ---------------------------------------------------------------------------
# Unit tests — save_suite / load_suite / list_suites / delete_suite
# ---------------------------------------------------------------------------


class TestSaveSuite:
    def test_creates_yaml_file(self, workspace: Path) -> None:
        em.save_suite(MINIMAL_SUITE, base=workspace)
        path = workspace / ".harness" / "evals" / "suites" / "code-review-suite.yaml"
        assert path.exists()

    def test_yaml_contents(self, workspace: Path) -> None:
        em.save_suite(MINIMAL_SUITE, base=workspace)
        path = workspace / ".harness" / "evals" / "suites" / "code-review-suite.yaml"
        loaded = yaml.safe_load(path.read_text())
        assert loaded["name"] == "code-review-suite"
        assert len(loaded["cases"]) == 1

    def test_overwrite_existing(self, workspace: Path) -> None:
        em.save_suite(MINIMAL_SUITE, base=workspace)
        updated = {**MINIMAL_SUITE, "description": "Updated desc"}
        em.save_suite(updated, base=workspace)
        loaded = em.load_suite("code-review-suite", base=workspace)
        assert loaded["description"] == "Updated desc"

    def test_raises_on_invalid_data(self, workspace: Path) -> None:
        with pytest.raises(ValueError, match="Invalid test suite"):
            em.save_suite({"name": "", "description": "", "cases": []}, base=workspace)

    def test_creates_suites_subdir(self, workspace: Path) -> None:
        em.save_suite(MINIMAL_SUITE, base=workspace)
        assert (workspace / ".harness" / "evals" / "suites").is_dir()


class TestLoadSuite:
    def test_load_saved_suite(self, workspace: Path) -> None:
        em.save_suite(MINIMAL_SUITE, base=workspace)
        data = em.load_suite("code-review-suite", base=workspace)
        assert data["name"] == "code-review-suite"

    def test_raises_on_missing(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            em.load_suite("nonexistent", base=workspace)

    def test_round_trip_preserves_assertions(self, workspace: Path) -> None:
        em.save_suite(MULTI_CASE_SUITE, base=workspace)
        data = em.load_suite("multi-case", base=workspace)
        assert len(data["cases"]) == 3
        types = [a["type"] for case in data["cases"] for a in case["assertions"]]
        assert "contains" in types
        assert "regex" in types
        assert "json_schema" in types


class TestListSuites:
    def test_empty(self, workspace: Path) -> None:
        assert em.list_suites(base=workspace) == []

    def test_lists_saved_suites(self, workspace: Path) -> None:
        em.save_suite(MINIMAL_SUITE, base=workspace)
        em.save_suite(MULTI_CASE_SUITE, base=workspace)
        names = em.list_suites(base=workspace)
        assert "code-review-suite" in names
        assert "multi-case" in names

    def test_sorted_alphabetically(self, workspace: Path) -> None:
        em.save_suite(MULTI_CASE_SUITE, base=workspace)
        em.save_suite(MINIMAL_SUITE, base=workspace)
        names = em.list_suites(base=workspace)
        assert names == sorted(names)


class TestDeleteSuite:
    def test_deletes_file(self, workspace: Path) -> None:
        em.save_suite(MINIMAL_SUITE, base=workspace)
        em.delete_suite("code-review-suite", base=workspace)
        assert not em.suite_file("code-review-suite", base=workspace).exists()

    def test_raises_on_missing(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            em.delete_suite("nonexistent", base=workspace)

    def test_not_in_list_after_delete(self, workspace: Path) -> None:
        em.save_suite(MINIMAL_SUITE, base=workspace)
        em.delete_suite("code-review-suite", base=workspace)
        assert "code-review-suite" not in em.list_suites(base=workspace)


# ---------------------------------------------------------------------------
# Unit tests — suite_summary
# ---------------------------------------------------------------------------


class TestSuiteSummary:
    def test_counts_cases_and_assertions(self) -> None:
        s = em.suite_summary(MULTI_CASE_SUITE)
        assert s["case_count"] == 3
        assert s["assertion_count"] == 3

    def test_returns_name_and_description(self) -> None:
        s = em.suite_summary(MINIMAL_SUITE)
        assert s["name"] == "code-review-suite"
        assert s["description"] == "代码审查测试集"


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestEvalSuiteAddCLI:
    def test_suite_add_from_file(self, workspace: Path, tmp_path: Path) -> None:
        suite_file = tmp_path / "suite.yaml"
        suite_file.write_text(yaml.dump(MINIMAL_SUITE), encoding="utf-8")
        result = runner.invoke(app, ["eval", "suite-add", "--file", str(suite_file)])
        assert result.exit_code == 0, result.output
        assert "code-review-suite" in result.output
        assert "1 cases" in result.output

    def test_suite_add_missing_file(self, workspace: Path) -> None:
        result = runner.invoke(app, ["eval", "suite-add", "--file", "/no/such/file.yaml"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_suite_add_invalid_suite(self, workspace: Path, tmp_path: Path) -> None:
        bad = {"name": "", "description": "", "cases": []}
        suite_file = tmp_path / "bad.yaml"
        suite_file.write_text(yaml.dump(bad), encoding="utf-8")
        result = runner.invoke(app, ["eval", "suite-add", "--file", str(suite_file)])
        assert result.exit_code != 0
        assert "Validation error" in result.output

    def test_suite_add_updates_existing(self, workspace: Path, tmp_path: Path) -> None:
        suite_file = tmp_path / "suite.yaml"
        suite_file.write_text(yaml.dump(MINIMAL_SUITE), encoding="utf-8")
        runner.invoke(app, ["eval", "suite-add", "--file", str(suite_file)])
        # overwrite with updated description
        updated = {**MINIMAL_SUITE, "description": "New desc"}
        suite_file.write_text(yaml.dump(updated), encoding="utf-8")
        result = runner.invoke(app, ["eval", "suite-add", "--file", str(suite_file)])
        assert result.exit_code == 0
        loaded = em.load_suite("code-review-suite", base=workspace)
        assert loaded["description"] == "New desc"


class TestEvalListCLI:
    def test_list_empty(self, workspace: Path) -> None:
        result = runner.invoke(app, ["eval", "list"])
        assert result.exit_code == 0
        assert "No test suites" in result.output

    def test_list_shows_suites(self, workspace: Path) -> None:
        em.save_suite(MINIMAL_SUITE, base=workspace)
        result = runner.invoke(app, ["eval", "list"])
        assert result.exit_code == 0
        assert "code-review-suite" in result.output

    def test_list_shows_case_count(self, workspace: Path) -> None:
        em.save_suite(MULTI_CASE_SUITE, base=workspace)
        result = runner.invoke(app, ["eval", "list"])
        assert result.exit_code == 0
        assert "3" in result.output  # 3 cases


class TestEvalShowCLI:
    def test_show_suite(self, workspace: Path) -> None:
        em.save_suite(MINIMAL_SUITE, base=workspace)
        result = runner.invoke(app, ["eval", "show", "code-review-suite"])
        assert result.exit_code == 0
        assert "detect-bug" in result.output
        assert "contains" in result.output

    def test_show_missing(self, workspace: Path) -> None:
        result = runner.invoke(app, ["eval", "show", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_show_displays_assertion_details(self, workspace: Path) -> None:
        em.save_suite(MINIMAL_SUITE, base=workspace)
        result = runner.invoke(app, ["eval", "show", "code-review-suite"])
        assert "ZeroDivisionError" in result.output


class TestEvalDeleteCLI:
    def test_delete_with_yes(self, workspace: Path) -> None:
        em.save_suite(MINIMAL_SUITE, base=workspace)
        result = runner.invoke(app, ["eval", "delete", "--yes", "code-review-suite"])
        assert result.exit_code == 0
        assert "deleted" in result.output.lower()
        assert em.list_suites(base=workspace) == []

    def test_delete_missing(self, workspace: Path) -> None:
        result = runner.invoke(app, ["eval", "delete", "--yes", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_delete_abort_on_no_confirm(self, workspace: Path) -> None:
        em.save_suite(MINIMAL_SUITE, base=workspace)
        result = runner.invoke(app, ["eval", "delete", "code-review-suite"], input="n\n")
        assert result.exit_code == 0
        assert "code-review-suite" in em.list_suites(base=workspace)


class TestMultiAssertionTypes:
    """Acceptance criteria: supports multiple assertion types."""

    def test_contains_assertion_saved(self, workspace: Path) -> None:
        data = {
            "name": "test-contains",
            "description": "test",
            "cases": [
                {"id": "c1", "name": "Contains check", "assertions": [{"type": "contains", "path": "$.x", "value": "v"}]}
            ],
        }
        em.save_suite(data, base=workspace)
        loaded = em.load_suite("test-contains", base=workspace)
        assert loaded["cases"][0]["assertions"][0]["type"] == "contains"

    def test_regex_assertion_saved(self, workspace: Path) -> None:
        data = {
            "name": "test-regex",
            "description": "test",
            "cases": [
                {"id": "c1", "name": "Regex check", "assertions": [{"type": "regex", "path": "$.x", "pattern": "foo"}]}
            ],
        }
        em.save_suite(data, base=workspace)
        loaded = em.load_suite("test-regex", base=workspace)
        assert loaded["cases"][0]["assertions"][0]["type"] == "regex"

    def test_json_schema_assertion_saved(self, workspace: Path) -> None:
        data = {
            "name": "test-jsonschema",
            "description": "test",
            "cases": [
                {
                    "id": "c1",
                    "name": "JSON Schema check",
                    "assertions": [
                        {"type": "json_schema", "path": "$.x", "schema": {"type": "string"}}
                    ],
                }
            ],
        }
        em.save_suite(data, base=workspace)
        loaded = em.load_suite("test-jsonschema", base=workspace)
        assert loaded["cases"][0]["assertions"][0]["type"] == "json_schema"
        assert loaded["cases"][0]["assertions"][0]["schema"] == {"type": "string"}

    def test_custom_assertion_saved(self, workspace: Path) -> None:
        data = {
            "name": "test-custom",
            "description": "test",
            "cases": [
                {
                    "id": "c1",
                    "name": "Custom check",
                    "assertions": [{"type": "custom", "function": "mymodule.check"}],
                }
            ],
        }
        em.save_suite(data, base=workspace)
        loaded = em.load_suite("test-custom", base=workspace)
        assert loaded["cases"][0]["assertions"][0]["function"] == "mymodule.check"
