"""Eval system — Test Suite data model, storage, and runner (Phase 5.1/5.3)."""

from __future__ import annotations

import json
import re
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from harness_kit.config import harness_dir


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def evals_dir(base: Path | None = None) -> Path:
    return harness_dir(base) / "evals"


def suites_dir(base: Path | None = None) -> Path:
    return evals_dir(base) / "suites"


def results_dir(base: Path | None = None) -> Path:
    return evals_dir(base) / "results"


def suite_file(name: str, base: Path | None = None) -> Path:
    return suites_dir(base) / f"{name}.yaml"


# ---------------------------------------------------------------------------
# Assertion validation helpers
# ---------------------------------------------------------------------------

_VALID_ASSERTION_TYPES = {"contains", "regex", "json_schema", "custom"}


def _validate_assertion(idx: int, a: Any) -> list[str]:
    """Validate a single assertion dict. Returns error strings."""
    errors: list[str] = []
    if not isinstance(a, dict):
        errors.append(f"assertions[{idx}]: must be a mapping, got {type(a).__name__}.")
        return errors

    atype = a.get("type")
    if not atype:
        errors.append(f"assertions[{idx}]: 'type' is required.")
    elif atype not in _VALID_ASSERTION_TYPES:
        valid = ", ".join(sorted(_VALID_ASSERTION_TYPES))
        errors.append(f"assertions[{idx}]: unsupported type '{atype}'. Valid: {valid}.")

    if atype == "contains":
        if not a.get("path"):
            errors.append(f"assertions[{idx}] (contains): 'path' is required.")
        if "value" not in a:
            errors.append(f"assertions[{idx}] (contains): 'value' is required.")

    elif atype == "regex":
        if not a.get("path"):
            errors.append(f"assertions[{idx}] (regex): 'path' is required.")
        pattern = a.get("pattern")
        if not pattern:
            errors.append(f"assertions[{idx}] (regex): 'pattern' is required.")
        else:
            try:
                re.compile(pattern)
            except re.error as exc:
                errors.append(f"assertions[{idx}] (regex): invalid pattern — {exc}.")

    elif atype == "json_schema":
        if not a.get("path"):
            errors.append(f"assertions[{idx}] (json_schema): 'path' is required.")
        if not a.get("schema"):
            errors.append(f"assertions[{idx}] (json_schema): 'schema' is required.")

    elif atype == "custom":
        if not a.get("function"):
            errors.append(f"assertions[{idx}] (custom): 'function' is required (e.g. 'mymodule.check').")

    return errors


def _validate_case(idx: int, case: Any) -> list[str]:
    """Validate a single test case dict. Returns error strings."""
    errors: list[str] = []
    if not isinstance(case, dict):
        errors.append(f"cases[{idx}]: must be a mapping, got {type(case).__name__}.")
        return errors

    if not case.get("id"):
        errors.append(f"cases[{idx}]: 'id' is required.")
    if not case.get("name"):
        errors.append(f"cases[{idx}]: 'name' is required.")

    inputs = case.get("inputs")
    if inputs is not None and not isinstance(inputs, dict):
        errors.append(f"cases[{idx}]: 'inputs' must be a mapping.")

    assertions = case.get("assertions")
    if assertions is None:
        errors.append(f"cases[{idx}] (id={case.get('id', '?')}): 'assertions' is required.")
    elif not isinstance(assertions, list):
        errors.append(f"cases[{idx}]: 'assertions' must be a list.")
    else:
        for aidx, a in enumerate(assertions):
            errors.extend(_validate_assertion(aidx, a))

    return errors


def _validate_suite_data(data: dict[str, Any]) -> list[str]:
    """Validate a test suite dict. Returns a list of error strings (empty = valid)."""
    errors: list[str] = []

    if not data.get("name"):
        errors.append("'name' is required.")
    if not data.get("description"):
        errors.append("'description' is required.")

    cases = data.get("cases")
    if cases is None:
        errors.append("'cases' is required.")
    elif not isinstance(cases, list):
        errors.append("'cases' must be a list.")
    elif len(cases) == 0:
        errors.append("'cases' must not be empty.")
    else:
        ids_seen: set[str] = set()
        for idx, case in enumerate(cases):
            errors.extend(_validate_case(idx, case))
            cid = case.get("id") if isinstance(case, dict) else None
            if cid:
                if cid in ids_seen:
                    errors.append(f"Duplicate case id '{cid}'.")
                ids_seen.add(cid)

    return errors


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


def save_suite(data: dict[str, Any], base: Path | None = None) -> None:
    """Persist a test suite. Overwrites if it already exists (no versioning)."""
    errors = _validate_suite_data(data)
    if errors:
        raise ValueError("Invalid test suite:\n" + "\n".join(f"  - {e}" for e in errors))

    name = data["name"]
    sdir = suites_dir(base)
    sdir.mkdir(parents=True, exist_ok=True)

    path = suite_file(name, base)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def load_suite(name: str, base: Path | None = None) -> dict[str, Any]:
    """Load a test suite by name. Raises FileNotFoundError if not found."""
    path = suite_file(name, base)
    if not path.exists():
        raise FileNotFoundError(f"Test suite '{name}' not found.")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def list_suites(base: Path | None = None) -> list[str]:
    """Return names of all saved test suites, sorted alphabetically."""
    sdir = suites_dir(base)
    if not sdir.exists():
        return []
    return sorted(p.stem for p in sdir.glob("*.yaml"))


def delete_suite(name: str, base: Path | None = None) -> None:
    """Delete a test suite. Raises FileNotFoundError if not found."""
    path = suite_file(name, base)
    if not path.exists():
        raise FileNotFoundError(f"Test suite '{name}' not found.")
    path.unlink()


# ---------------------------------------------------------------------------
# Render helpers (for display)
# ---------------------------------------------------------------------------


def suite_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Return a display-friendly summary of a test suite."""
    cases = data.get("cases") or []
    assertion_count = sum(len(c.get("assertions") or []) for c in cases if isinstance(c, dict))
    return {
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "case_count": len(cases),
        "assertion_count": assertion_count,
    }


# ---------------------------------------------------------------------------
# Eval runner (Phase 5.3)
# ---------------------------------------------------------------------------


def _parse_output(text: str) -> Any:
    """Try to parse LLM output text as JSON. Falls back to the raw string."""
    stripped = text.strip()
    # Direct JSON object or array
    if stripped.startswith(("{", "[")):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    # Markdown fenced code block
    m = re.search(r"```(?:json)?\s*\n([\s\S]*?)\n?```", stripped)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    return text  # return as plain string


def run_eval(
    target: str,
    suite_name: str,
    invoke_fn: Callable[[dict[str, Any]], tuple[str, int, int, float]],
    base: Path | None = None,
) -> dict[str, Any]:
    """Run a test suite against a skill or harness.

    Parameters
    ----------
    target:
        Display label for the target (e.g. ``'code-reviewer@v0.1.0'``).
    suite_name:
        Name of the test suite to execute.
    invoke_fn:
        Callable ``(inputs: dict) -> (output_text, input_tokens, output_tokens, duration)``.
        Responsible for calling the LLM/skill/harness and returning its raw output.
    base:
        Optional path override for the ``.harness/`` directory root.

    Returns
    -------
    dict
        Full evaluation report (also persisted to ``.harness/evals/results/``).
    """
    from harness_kit.assertions import run_assertions, assertions_passed, assertion_summary

    suite = load_suite(suite_name, base)
    cases = suite.get("cases") or []
    timestamp = datetime.now(timezone.utc).isoformat()

    case_results: list[dict[str, Any]] = []
    total_passed = 0
    total_failed = 0

    for case in cases:
        case_id = case.get("id", "?")
        case_name = case.get("name", "")
        inputs: dict[str, Any] = case.get("inputs") or {}
        assertions = case.get("assertions") or []

        case_result: dict[str, Any] = {
            "id": case_id,
            "name": case_name,
            "status": "error",
            "duration": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "assertions": [],
        }

        try:
            output_text, input_tokens, output_tokens, duration = invoke_fn(inputs)
            case_result["duration"] = round(duration, 3)
            case_result["input_tokens"] = input_tokens
            case_result["output_tokens"] = output_tokens
            case_result["output_preview"] = output_text[:200]

            data = _parse_output(output_text)

            assertion_results = run_assertions(assertions, data)
            passed = assertions_passed(assertion_results)
            summary = assertion_summary(assertion_results)

            case_result["status"] = "passed" if passed else "failed"
            case_result["assertions"] = [
                {
                    "type": r.assertion_type,
                    "path": r.path,
                    "passed": r.passed,
                    "message": r.message,
                }
                for r in assertion_results
            ]
            case_result["assertion_summary"] = summary

            if passed:
                total_passed += 1
            else:
                total_failed += 1

        except Exception as exc:
            case_result["status"] = "error"
            case_result["error"] = str(exc)
            total_failed += 1

        case_results.append(case_result)

    total = len(cases)
    report: dict[str, Any] = {
        "timestamp": timestamp,
        "target": target,
        "suite": suite_name,
        "summary": {
            "total": total,
            "passed": total_passed,
            "failed": total_failed,
        },
        "cases": case_results,
    }

    # Persist result
    rdir = results_dir(base)
    rdir.mkdir(parents=True, exist_ok=True)
    # Build filesystem-safe timestamp string
    ts_safe = re.sub(r"[:\+\.]", "-", timestamp)[:23]
    result_file = rdir / f"{ts_safe}.json"
    with result_file.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    report["_result_file"] = str(result_file)
    return report


# ---------------------------------------------------------------------------
# A/B Comparison (Phase 5.4)
# ---------------------------------------------------------------------------


def _report_metrics(report: dict[str, Any]) -> dict[str, Any]:
    """Compute aggregate metrics from a run_eval report."""
    cases = report.get("cases") or []
    total = len(cases)
    passed = sum(1 for c in cases if c.get("status") == "passed")
    failed = total - passed
    pass_rate = round(passed / total, 4) if total > 0 else 0.0
    total_tokens = sum(c.get("input_tokens", 0) + c.get("output_tokens", 0) for c in cases)
    avg_tokens = round(total_tokens / total, 1) if total > 0 else 0.0
    total_dur = sum(c.get("duration", 0.0) for c in cases)
    avg_dur = round(total_dur / total, 3) if total > 0 else 0.0
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
        "total_tokens": total_tokens,
        "avg_tokens": avg_tokens,
        "total_duration": round(total_dur, 3),
        "avg_duration": avg_dur,
    }


def compare_evals(report_a: dict[str, Any], report_b: dict[str, Any]) -> dict[str, Any]:
    """Compare two eval reports (A/B) and produce a structured comparison.

    Parameters
    ----------
    report_a, report_b:
        Reports returned by :func:`run_eval`.

    Returns
    -------
    dict with keys:
        target_a, target_b, suite, metrics_a, metrics_b,
        case_diffs, changed_cases, verdict
    """
    m_a = _report_metrics(report_a)
    m_b = _report_metrics(report_b)

    # Per-case diff
    cases_a = {c["id"]: c for c in (report_a.get("cases") or [])}
    cases_b = {c["id"]: c for c in (report_b.get("cases") or [])}
    all_ids = sorted(set(cases_a) | set(cases_b))

    case_diffs: list[dict[str, Any]] = []
    for cid in all_ids:
        ca = cases_a.get(cid)
        cb = cases_b.get(cid)
        status_a = ca["status"] if ca else "missing"
        status_b = cb["status"] if cb else "missing"
        case_diffs.append(
            {
                "id": cid,
                "name": (ca or cb or {}).get("name", ""),
                "status_a": status_a,
                "status_b": status_b,
                "changed": status_a != status_b,
            }
        )

    # Verdict: prefer higher pass_rate; tie-break on lower avg_tokens
    if m_b["pass_rate"] > m_a["pass_rate"]:
        verdict = "b"
    elif m_a["pass_rate"] > m_b["pass_rate"]:
        verdict = "a"
    elif m_a["avg_tokens"] <= m_b["avg_tokens"]:
        verdict = "a"
    else:
        verdict = "b"

    return {
        "target_a": report_a.get("target", ""),
        "target_b": report_b.get("target", ""),
        "suite": report_a.get("suite", report_b.get("suite", "")),
        "metrics_a": m_a,
        "metrics_b": m_b,
        "case_diffs": case_diffs,
        "changed_cases": [d for d in case_diffs if d["changed"]],
        "verdict": verdict,
    }
