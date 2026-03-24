"""Eval system — Test Suite data model and storage (Phase 5.1)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

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
