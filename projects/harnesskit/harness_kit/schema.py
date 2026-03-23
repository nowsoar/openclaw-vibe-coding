"""Schema asset management — data model and storage (JSON format)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_kit.config import harness_dir


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def schemas_dir(base: Path | None = None) -> Path:
    return harness_dir(base) / "schemas"


def schema_dir(name: str, base: Path | None = None) -> Path:
    return schemas_dir(base) / name


def _current_file(name: str, base: Path | None = None) -> Path:
    return schema_dir(name, base) / "_current"


def _version_file(name: str, version: str, base: Path | None = None) -> Path:
    return schema_dir(name, base) / f"{version}.json"


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------


def _parse_version(version: str) -> tuple[int, int, int]:
    """'v1.2.3' -> (1, 2, 3)"""
    v = version.lstrip("v")
    parts = v.split(".")
    return int(parts[0]), int(parts[1]), int(parts[2])


def _bump_patch(version: str) -> str:
    major, minor, patch = _parse_version(version)
    return f"v{major}.{minor}.{patch + 1}"


def get_current_version(name: str, base: Path | None = None) -> str | None:
    cf = _current_file(name, base)
    return cf.read_text(encoding="utf-8").strip() if cf.exists() else None


def list_versions(name: str, base: Path | None = None) -> list[str]:
    d = schema_dir(name, base)
    if not d.exists():
        return []
    versions = [f.stem for f in d.glob("v*.json")]
    versions.sort(key=_parse_version)
    return versions


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def save_schema(
    name: str,
    parameters: dict[str, Any],
    description: str = "",
    tags: list[str] | None = None,
    changelog: str = "",
    base: Path | None = None,
) -> tuple[str, bool]:
    """Save (or update) a schema. Returns (new_version, is_new_schema)."""
    d = schema_dir(name, base)
    d.mkdir(parents=True, exist_ok=True)

    current = get_current_version(name, base)
    is_new = current is None
    new_version = "v0.0.1" if is_new else _bump_patch(current)

    data: dict[str, Any] = {
        "name": name,
        "version": new_version,
        "description": description,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "tags": tags or [],
        "parameters": parameters,
        "changelog": changelog,
    }

    with _version_file(name, new_version, base).open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    _current_file(name, base).write_text(new_version, encoding="utf-8")
    return new_version, is_new


def load_schema(
    name: str,
    version: str | None = None,
    base: Path | None = None,
) -> dict[str, Any]:
    """Load a schema by name (and optional version). Raises FileNotFoundError."""
    if version is None:
        version = get_current_version(name, base)
        if version is None:
            raise FileNotFoundError(f"Schema '{name}' not found.")

    vf = _version_file(name, version, base)
    if not vf.exists():
        raise FileNotFoundError(f"Schema '{name}@{version}' not found.")

    with vf.open("r", encoding="utf-8") as f:
        return json.load(f)


def list_schemas(base: Path | None = None) -> list[dict[str, Any]]:
    """Return current version metadata for every schema."""
    sd = schemas_dir(base)
    if not sd.exists():
        return []

    result = []
    for d in sorted(sd.iterdir()):
        if not d.is_dir():
            continue
        current = get_current_version(d.name, base)
        if current:
            try:
                result.append(load_schema(d.name, current, base))
            except Exception:
                pass
    return result


def delete_schema(
    name: str,
    version: str | None = None,
    base: Path | None = None,
) -> None:
    """Delete a schema or a specific version of it."""
    d = schema_dir(name, base)
    if not d.exists():
        raise FileNotFoundError(f"Schema '{name}' not found.")

    if version is None:
        shutil.rmtree(d)
        return

    vf = _version_file(name, version, base)
    if not vf.exists():
        raise FileNotFoundError(f"Schema '{name}@{version}' not found.")

    vf.unlink()

    # Re-point _current if we deleted the current version
    current = get_current_version(name, base)
    if current == version:
        remaining = list_versions(name, base)
        if remaining:
            _current_file(name, base).write_text(remaining[-1], encoding="utf-8")
        else:
            _current_file(name, base).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------


def validate_schema(name: str, base: Path | None = None) -> list[str]:
    """Validate the schema's `parameters` field against JSON Schema meta-schema.

    Returns a list of error messages. Empty list means valid.
    """
    data = load_schema(name, base=base)
    parameters = data.get("parameters")

    if parameters is None:
        return ["Missing 'parameters' field in schema."]
    if not isinstance(parameters, dict):
        return ["'parameters' must be a JSON object."]

    try:
        import jsonschema
        jsonschema.Draft7Validator.check_schema(parameters)
        return []
    except ImportError:
        # Fallback: basic structural check without jsonschema library
        return _basic_schema_check(parameters)
    except jsonschema.SchemaError as e:
        return [f"JSON Schema error at {' > '.join(str(p) for p in e.absolute_path) or 'root'}: {e.message}"]


def _basic_schema_check(parameters: dict[str, Any]) -> list[str]:
    """Minimal structural validation when jsonschema is not available."""
    errors: list[str] = []
    valid_types = {"object", "array", "string", "number", "integer", "boolean", "null"}

    if "type" in parameters:
        t = parameters["type"]
        if isinstance(t, str) and t not in valid_types:
            errors.append(f"Invalid type '{t}'. Must be one of: {', '.join(sorted(valid_types))}.")
        elif isinstance(t, list):
            for item in t:
                if item not in valid_types:
                    errors.append(f"Invalid type '{item}' in type array.")

    if "properties" in parameters and not isinstance(parameters["properties"], dict):
        errors.append("'properties' must be an object.")

    if "required" in parameters:
        req = parameters["required"]
        if not isinstance(req, list):
            errors.append("'required' must be an array.")
        elif not all(isinstance(r, str) for r in req):
            errors.append("All items in 'required' must be strings.")

    return errors
