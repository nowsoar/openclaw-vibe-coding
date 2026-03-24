"""Tests for harness_kit/assertions.py (Phase 5.2)."""

from __future__ import annotations

from typing import Any

import pytest

from harness_kit.assertions import (
    AssertionResult,
    assertion_summary,
    assertions_passed,
    run_assertion,
    run_assertions,
    _resolve_path,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def code_review_data() -> dict[str, Any]:
    """Sample parsed LLM output resembling a code-review response."""
    return {
        "issues": [
            {"type": "ZeroDivisionError", "severity": "high", "message": "除零风险"},
            {"type": "NameError", "severity": "medium", "message": "未定义变量"},
        ],
        "summary": "发现 2 个问题，需要异常处理 (error handling) 改进。",
    }


# ---------------------------------------------------------------------------
# _resolve_path unit tests
# ---------------------------------------------------------------------------


class TestResolvePath:
    def test_root_path_returns_whole_doc(self) -> None:
        data = {"a": 1}
        result = _resolve_path("$", data)
        assert result == [{"a": 1}]

    def test_nested_key(self) -> None:
        data = {"user": {"name": "Alice"}}
        result = _resolve_path("$.user.name", data)
        assert result == ["Alice"]

    def test_wildcard_array(self) -> None:
        data = {"items": [{"type": "A"}, {"type": "B"}]}
        result = _resolve_path("$.items[*].type", data)
        assert result == ["A", "B"]

    def test_no_matches_returns_empty(self) -> None:
        data = {"a": 1}
        result = _resolve_path("$.b.c.d", data)
        assert result == []

    def test_invalid_path_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid JSONPath"):
            _resolve_path("[[[invalid", {"a": 1})

    def test_path_on_non_dict_returns_empty(self) -> None:
        # JSONPath cannot navigate into a plain string
        result = _resolve_path("$.key", "plain string")
        assert result == []


# ---------------------------------------------------------------------------
# contains assertion
# ---------------------------------------------------------------------------


class TestContainsAssertion:
    def test_exact_match_in_list(self, code_review_data: dict) -> None:
        assertion = {
            "type": "contains",
            "path": "$.issues[*].type",
            "value": "ZeroDivisionError",
        }
        result = run_assertion(assertion, code_review_data)
        assert result.passed
        assert result.assertion_type == "contains"
        assert "OK" in result.message

    def test_value_not_in_list(self, code_review_data: dict) -> None:
        assertion = {
            "type": "contains",
            "path": "$.issues[*].type",
            "value": "TypeError",
        }
        result = run_assertion(assertion, code_review_data)
        assert not result.passed
        assert "FAIL" in result.message
        assert "TypeError" in result.message

    def test_substring_in_string(self, code_review_data: dict) -> None:
        assertion = {
            "type": "contains",
            "path": "$.summary",
            "value": "error handling",
        }
        result = run_assertion(assertion, code_review_data)
        assert result.passed

    def test_exact_string_equality(self) -> None:
        data = {"status": "passed"}
        assertion = {"type": "contains", "path": "$.status", "value": "passed"}
        result = run_assertion(assertion, data)
        assert result.passed

    def test_no_path_uses_root_data(self) -> None:
        assertion = {"type": "contains", "value": "hello"}
        result = run_assertion(assertion, "hello world")
        assert result.passed

    def test_path_matches_nothing_fails(self) -> None:
        data = {}
        assertion = {"type": "contains", "path": "$.missing", "value": "x"}
        result = run_assertion(assertion, data)
        assert not result.passed

    def test_result_fields(self, code_review_data: dict) -> None:
        assertion = {
            "type": "contains",
            "path": "$.issues[*].severity",
            "value": "high",
        }
        result = run_assertion(assertion, code_review_data)
        assert result.passed
        assert result.path == "$.issues[*].severity"
        assert result.expected == "high"

    def test_value_in_nested_list_match(self) -> None:
        # The jsonpath returns a list for each item; value should be found
        data = {"tags": ["python", "security", "performance"]}
        assertion = {
            "type": "contains",
            "path": "$.tags",
            "value": "security",
        }
        result = run_assertion(assertion, data)
        assert result.passed


# ---------------------------------------------------------------------------
# regex assertion
# ---------------------------------------------------------------------------


class TestRegexAssertion:
    def test_pattern_matches_string(self, code_review_data: dict) -> None:
        assertion = {
            "type": "regex",
            "path": "$.summary",
            "pattern": r"异常处理|error handling",
        }
        result = run_assertion(assertion, code_review_data)
        assert result.passed

    def test_pattern_does_not_match(self) -> None:
        data = {"text": "everything is fine"}
        assertion = {"type": "regex", "path": "$.text", "pattern": r"error|failure"}
        result = run_assertion(assertion, data)
        assert not result.passed
        assert "FAIL" in result.message

    def test_matches_any_item_in_list(self) -> None:
        data = {"messages": [{"text": "hello world"}, {"text": "foo bar"}]}
        assertion = {
            "type": "regex",
            "path": "$.messages[*].text",
            "pattern": r"hello",
        }
        result = run_assertion(assertion, data)
        assert result.passed

    def test_no_path_uses_root_string(self) -> None:
        assertion = {"type": "regex", "pattern": r"\d+"}
        result = run_assertion(assertion, "version 42 released")
        assert result.passed

    def test_invalid_pattern_returns_failure(self) -> None:
        data = {"x": "hello"}
        assertion = {"type": "regex", "path": "$.x", "pattern": "[invalid"}
        result = run_assertion(assertion, data)
        assert not result.passed
        assert "invalid regex" in result.message.lower()

    def test_pattern_on_integer_value(self) -> None:
        data = {"code": 404}
        assertion = {"type": "regex", "path": "$.code", "pattern": r"4\d\d"}
        result = run_assertion(assertion, data)
        assert result.passed  # integer coerced to str "404"

    def test_case_insensitive_via_flag(self) -> None:
        data = {"msg": "Error occurred"}
        assertion = {"type": "regex", "path": "$.msg", "pattern": r"(?i)error"}
        result = run_assertion(assertion, data)
        assert result.passed


# ---------------------------------------------------------------------------
# json_schema assertion
# ---------------------------------------------------------------------------


class TestJsonSchemaAssertion:
    def test_valid_object_passes(self) -> None:
        data = {"name": "Alice", "age": 30}
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name", "age"],
        }
        assertion = {"type": "json_schema", "path": "$", "schema": schema}
        result = run_assertion(assertion, data)
        assert result.passed

    def test_invalid_type_fails(self) -> None:
        data = {"age": "not-a-number"}
        schema = {
            "type": "object",
            "properties": {"age": {"type": "integer"}},
            "required": ["age"],
        }
        assertion = {"type": "json_schema", "path": "$", "schema": schema}
        result = run_assertion(assertion, data)
        assert not result.passed
        assert "FAIL" in result.message

    def test_missing_required_field_fails(self) -> None:
        data = {"age": 25}
        schema = {"type": "object", "required": ["name"]}
        assertion = {"type": "json_schema", "path": "$", "schema": schema}
        result = run_assertion(assertion, data)
        assert not result.passed

    def test_path_matches_nothing_fails(self) -> None:
        data = {}
        schema = {"type": "string"}
        assertion = {"type": "json_schema", "path": "$.missing", "schema": schema}
        result = run_assertion(assertion, data)
        assert not result.passed
        assert "matched nothing" in result.message

    def test_nested_path(self) -> None:
        data = {
            "issues": [
                {"type": "ZeroDivisionError", "severity": "high"},
            ]
        }
        schema = {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "severity": {"type": "string"},
            },
            "required": ["type", "severity"],
        }
        # Validates the first element of issues array
        assertion = {"type": "json_schema", "path": "$.issues[0]", "schema": schema}
        result = run_assertion(assertion, data)
        assert result.passed

    def test_result_contains_actual_value(self) -> None:
        data = {"score": 0.95}
        schema = {"type": "number", "minimum": 0, "maximum": 1}
        assertion = {"type": "json_schema", "path": "$.score", "schema": schema}
        result = run_assertion(assertion, data)
        assert result.passed
        assert result.actual == 0.95


# ---------------------------------------------------------------------------
# custom assertion
# ---------------------------------------------------------------------------


class TestCustomAssertion:
    def test_passing_stdlib_function(self) -> None:
        # builtins.bool("hello") → True
        assertion = {"type": "custom", "function": "builtins.bool"}
        result = run_assertion(assertion, "hello")
        assert result.passed

    def test_failing_stdlib_function(self) -> None:
        # builtins.bool("") → False
        assertion = {"type": "custom", "function": "builtins.bool"}
        result = run_assertion(assertion, "")
        assert not result.passed

    def test_with_path_extracts_value(self) -> None:
        # bool(42) → True
        data = {"count": 42}
        assertion = {"type": "custom", "path": "$.count", "function": "builtins.bool"}
        result = run_assertion(assertion, data)
        assert result.passed

    def test_with_path_zero_value_fails(self) -> None:
        # bool(0) → False
        data = {"count": 0}
        assertion = {"type": "custom", "path": "$.count", "function": "builtins.bool"}
        result = run_assertion(assertion, data)
        assert not result.passed

    def test_nonexistent_module_returns_failure(self) -> None:
        assertion = {"type": "custom", "function": "nonexistent_xyz.check_fn"}
        result = run_assertion(assertion, "data")
        assert not result.passed
        assert "FAIL" in result.message

    def test_error_message_contains_exception(self) -> None:
        assertion = {"type": "custom", "function": "no_such_module_abc.fn"}
        result = run_assertion(assertion, "x")
        assert not result.passed
        assert "FAIL" in result.message

    def test_path_no_match_passes_none(self) -> None:
        # bool(None) → False
        data = {}
        assertion = {
            "type": "custom",
            "path": "$.missing",
            "function": "builtins.bool",
        }
        result = run_assertion(assertion, data)
        assert not result.passed  # bool(None) is False


# ---------------------------------------------------------------------------
# unknown / unsupported type
# ---------------------------------------------------------------------------


class TestUnknownAssertionType:
    def test_unknown_type_returns_failure(self) -> None:
        result = run_assertion(
            {"type": "similarity", "path": "$.text", "threshold": 0.9},
            {"text": "hello"},
        )
        assert not result.passed
        assert "unsupported" in result.message

    def test_empty_type_returns_failure(self) -> None:
        result = run_assertion({"path": "$.x"}, {"x": "y"})
        assert not result.passed

    def test_assertion_type_field_is_set(self) -> None:
        result = run_assertion({"type": "future_type", "path": "$"}, {})
        assert result.assertion_type == "future_type"


# ---------------------------------------------------------------------------
# run_assertions (batch)
# ---------------------------------------------------------------------------


class TestRunAssertions:
    def test_empty_list_returns_empty(self) -> None:
        results = run_assertions([], {"a": 1})
        assert results == []

    def test_all_pass(self, code_review_data: dict) -> None:
        assertions = [
            {
                "type": "contains",
                "path": "$.issues[*].type",
                "value": "ZeroDivisionError",
            },
            {
                "type": "regex",
                "path": "$.summary",
                "pattern": r"异常处理|error handling",
            },
        ]
        results = run_assertions(assertions, code_review_data)
        assert len(results) == 2
        assert assertions_passed(results)

    def test_one_fails(self, code_review_data: dict) -> None:
        assertions = [
            {
                "type": "contains",
                "path": "$.issues[*].type",
                "value": "ZeroDivisionError",
            },
            {
                "type": "contains",
                "path": "$.issues[*].type",
                "value": "AttributeError",  # not present
            },
        ]
        results = run_assertions(assertions, code_review_data)
        assert results[0].passed
        assert not results[1].passed
        assert not assertions_passed(results)

    def test_preserves_order(self) -> None:
        data = {"x": "value"}
        assertions = [
            {"type": "contains", "path": "$.x", "value": "value"},
            {"type": "regex", "path": "$.x", "pattern": r"\d+"},  # fails
            {"type": "json_schema", "path": "$.x", "schema": {"type": "string"}},
        ]
        results = run_assertions(assertions, data)
        assert results[0].passed
        assert not results[1].passed
        assert results[2].passed


# ---------------------------------------------------------------------------
# assertions_passed helper
# ---------------------------------------------------------------------------


class TestAssertionsPassed:
    def test_all_passed(self) -> None:
        results = [
            AssertionResult(True, "contains", "$", "x", "x", "OK"),
            AssertionResult(True, "regex", "$", "p", "v", "OK"),
        ]
        assert assertions_passed(results)

    def test_one_failed(self) -> None:
        results = [
            AssertionResult(True, "contains", "$", "x", "x", "OK"),
            AssertionResult(False, "regex", "$", "p", "v", "FAIL"),
        ]
        assert not assertions_passed(results)

    def test_empty_is_true(self) -> None:
        assert assertions_passed([])


# ---------------------------------------------------------------------------
# assertion_summary helper
# ---------------------------------------------------------------------------


class TestAssertionSummary:
    def test_all_passed(self) -> None:
        results = [
            AssertionResult(True, "contains", "$", "x", "x", "OK"),
            AssertionResult(True, "regex", "$", "p", "v", "OK"),
        ]
        s = assertion_summary(results)
        assert s == {"total": 2, "passed": 2, "failed": 0}

    def test_mixed(self, code_review_data: dict) -> None:
        assertions = [
            {"type": "contains", "path": "$.issues[*].type", "value": "ZeroDivisionError"},
            {"type": "contains", "path": "$.issues[*].type", "value": "NoSuchError"},
        ]
        results = run_assertions(assertions, code_review_data)
        s = assertion_summary(results)
        assert s["total"] == 2
        assert s["passed"] == 1
        assert s["failed"] == 1

    def test_empty(self) -> None:
        s = assertion_summary([])
        assert s == {"total": 0, "passed": 0, "failed": 0}


# ---------------------------------------------------------------------------
# ROADMAP acceptance criteria scenarios
# ---------------------------------------------------------------------------


class TestRoadmapScenarios:
    """End-to-end scenarios from Phase 5.1 ROADMAP test suite definition."""

    def test_detect_zero_division_bug(self) -> None:
        """Simulates assertions for the 'detect-bug' test case in ROADMAP."""
        # Simulated LLM output (already parsed from JSON)
        llm_output = {
            "issues": [
                {
                    "type": "ZeroDivisionError",
                    "severity": "high",
                    "message": "除零风险",
                }
            ],
            "summary": "发现除零异常，需要 error handling 改进",
        }
        assertions = [
            {
                "type": "contains",
                "path": "$.issues[*].type",
                "value": "ZeroDivisionError",
            },
            {
                "type": "contains",
                "path": "$.issues[*].severity",
                "value": "high",
            },
            {
                "type": "regex",
                "path": "$.summary",
                "pattern": r"异常处理|error handling",
            },
        ]
        results = run_assertions(assertions, llm_output)
        assert assertions_passed(results), [r.message for r in results if not r.passed]

    def test_empty_function_check(self) -> None:
        """Simulates assertions for the 'empty-function' test case in ROADMAP."""
        llm_output = {
            "issues": [
                {
                    "type": "MissingImplementation",
                    "severity": "low",
                    "message": "缺少实现",
                }
            ]
        }
        assertions = [
            {
                "type": "contains",
                "path": "$.issues[*].message",
                "value": "缺少实现",
            },
        ]
        results = run_assertions(assertions, llm_output)
        assert assertions_passed(results)

    def test_json_schema_validates_issue_structure(self) -> None:
        """JSON Schema assertion validates that each issue has required fields."""
        llm_output = {
            "issues": [
                {"type": "ZeroDivisionError", "severity": "high", "message": "除零风险"}
            ]
        }
        issue_schema = {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                "message": {"type": "string"},
            },
            "required": ["type", "severity", "message"],
        }
        assertion = {
            "type": "json_schema",
            "path": "$.issues[0]",
            "schema": issue_schema,
        }
        result = run_assertion(assertion, llm_output)
        assert result.passed

    def test_all_assertion_types_integrated(self) -> None:
        """Verify all four assertion types can be used in a single run."""
        data = {"result": "test passed", "count": 5, "items": ["a", "b"]}

        assertions = [
            # contains: exact match
            {"type": "contains", "path": "$.result", "value": "test passed"},
            # regex: pattern match
            {"type": "regex", "path": "$.result", "pattern": r"pass"},
            # json_schema: type check
            {
                "type": "json_schema",
                "path": "$.count",
                "schema": {"type": "integer", "minimum": 1},
            },
            # custom: bool check
            {"type": "custom", "path": "$.count", "function": "builtins.bool"},
        ]
        results = run_assertions(assertions, data)
        assert len(results) == 4
        assert assertions_passed(results), [r.message for r in results if not r.passed]
