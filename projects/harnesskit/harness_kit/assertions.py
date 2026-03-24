"""Assertion engine for HarnessKit eval system (Phase 5.2).

Supported assertion types:
  - contains    : JSONPath value equals or contains the expected value
  - regex       : JSONPath value matches a regular expression
  - json_schema : JSONPath value validates against a JSON Schema
  - custom      : a user-supplied Python function returns truthy

Usage::

    from harness_kit.assertions import run_assertions, assertions_passed

    data = {"issues": [{"type": "ZeroDivisionError", "severity": "high"}]}
    results = run_assertions(suite_case["assertions"], data)
    if assertions_passed(results):
        print("all assertions passed")
    else:
        for r in results:
            if not r.passed:
                print(r.message)
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from typing import Any

import jsonschema
from jsonpath_ng import parse as _jsonpath_parse
from jsonpath_ng.exceptions import JsonPathParserError


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class AssertionResult:
    """Result of evaluating a single assertion."""

    passed: bool
    assertion_type: str
    path: str | None
    expected: Any
    actual: Any
    message: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_path(path: str, data: Any) -> list[Any]:
    """Return all values matched by *path* in *data* using JSONPath.

    Returns an empty list if nothing matches or if the path is invalid.
    Raises ValueError for a syntactically invalid path.
    """
    try:
        expr = _jsonpath_parse(path)
        matches = expr.find(data)
        return [m.value for m in matches]
    except JsonPathParserError as exc:
        raise ValueError(f"Invalid JSONPath '{path}': {exc}") from exc
    except Exception:
        return []


def _contains_value(match: Any, value: Any) -> bool:
    """Return True if *match* 'contains' *value* in a meaningful sense:

    - exact equality
    - *match* is a string and *value* is a substring
    - *match* is a list and *value* is an element
    """
    if match == value:
        return True
    if isinstance(match, str) and isinstance(value, str) and value in match:
        return True
    if isinstance(match, list) and value in match:
        return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_assertion(assertion: dict[str, Any], data: Any) -> AssertionResult:
    """Evaluate a single *assertion* dict against *data*.

    Parameters
    ----------
    assertion:
        A dict with at least a ``type`` key and type-specific fields.
    data:
        The value to test (typically parsed JSON / dict from an LLM call).

    Returns
    -------
    AssertionResult
        Always returns a result — never raises for evaluation logic errors.
    """
    atype: str = assertion.get("type", "")
    path: str | None = assertion.get("path")

    # ---- contains -----------------------------------------------------------
    if atype == "contains":
        value = assertion.get("value")
        matches = _resolve_path(path, data) if path else [data]
        passed = any(_contains_value(m, value) for m in matches)
        if passed:
            msg = f"OK — '{path}' contains {value!r}"
        else:
            msg = f"FAIL — '{path}' does not contain {value!r}. Actual: {matches!r}"
        return AssertionResult(
            passed=passed,
            assertion_type="contains",
            path=path,
            expected=value,
            actual=matches,
            message=msg,
        )

    # ---- regex --------------------------------------------------------------
    if atype == "regex":
        pattern: str = assertion.get("pattern", "")
        matches = _resolve_path(path, data) if path else [data]
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return AssertionResult(
                passed=False,
                assertion_type="regex",
                path=path,
                expected=pattern,
                actual=matches,
                message=f"FAIL — invalid regex pattern: {exc}",
            )
        matched_strs = [m if isinstance(m, str) else str(m) for m in matches]
        passed = any(regex.search(s) for s in matched_strs)
        if passed:
            msg = f"OK — '{path}' matches r{pattern!r}"
        else:
            msg = f"FAIL — '{path}' does not match r{pattern!r}. Actual: {matches!r}"
        return AssertionResult(
            passed=passed,
            assertion_type="regex",
            path=path,
            expected=pattern,
            actual=matches,
            message=msg,
        )

    # ---- json_schema --------------------------------------------------------
    if atype == "json_schema":
        schema: dict = assertion.get("schema", {})
        matches = _resolve_path(path, data) if path else [data]
        if not matches:
            return AssertionResult(
                passed=False,
                assertion_type="json_schema",
                path=path,
                expected=schema,
                actual=None,
                message=f"FAIL — '{path}' matched nothing.",
            )
        target = matches[0]
        try:
            jsonschema.validate(instance=target, schema=schema)
            passed = True
            msg = f"OK — '{path}' value passes JSON Schema validation"
        except jsonschema.ValidationError as exc:
            passed = False
            msg = f"FAIL — JSON Schema validation error: {exc.message}"
        return AssertionResult(
            passed=passed,
            assertion_type="json_schema",
            path=path,
            expected=schema,
            actual=target,
            message=msg,
        )

    # ---- custom -------------------------------------------------------------
    if atype == "custom":
        func_path: str = assertion.get("function", "")
        target: Any
        if path:
            matches = _resolve_path(path, data)
            target = matches[0] if matches else None
        else:
            target = data
        try:
            module_name, fn_name = func_path.rsplit(".", 1)
            mod = importlib.import_module(module_name)
            fn = getattr(mod, fn_name)
            result = fn(target)
            passed = bool(result)
            verdict = "OK" if passed else "FAIL"
            msg = f"{verdict} — custom function '{func_path}' returned {result!r}"
        except Exception as exc:
            passed = False
            target = None
            msg = f"FAIL — custom function '{func_path}' raised {type(exc).__name__}: {exc}"
        return AssertionResult(
            passed=passed,
            assertion_type="custom",
            path=path,
            expected=func_path,
            actual=target,
            message=msg,
        )

    # ---- unknown type -------------------------------------------------------
    return AssertionResult(
        passed=False,
        assertion_type=atype or "unknown",
        path=path,
        expected=None,
        actual=data,
        message=f"FAIL — unsupported assertion type '{atype}'.",
    )


def run_assertions(
    assertions: list[dict[str, Any]],
    data: Any,
) -> list[AssertionResult]:
    """Run every assertion in *assertions* against *data*.

    Parameters
    ----------
    assertions:
        List of assertion dicts (from a test suite case).
    data:
        The value under test (typically parsed JSON from an LLM response).

    Returns
    -------
    list[AssertionResult]
        One result per assertion, in order.
    """
    return [run_assertion(a, data) for a in assertions]


def assertions_passed(results: list[AssertionResult]) -> bool:
    """Return ``True`` if every result in *results* passed."""
    return all(r.passed for r in results)


def assertion_summary(results: list[AssertionResult]) -> dict[str, int]:
    """Return a ``{total, passed, failed}`` count dict."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    return {"total": total, "passed": passed, "failed": total - passed}
