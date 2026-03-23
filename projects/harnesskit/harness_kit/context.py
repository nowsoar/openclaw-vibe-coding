"""Context template asset management — data model and storage (YAML + Jinja2)."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from harness_kit.config import harness_dir


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def contexts_dir(base: Path | None = None) -> Path:
    return harness_dir(base) / "contexts"


def context_dir(name: str, base: Path | None = None) -> Path:
    return contexts_dir(base) / name


def _current_file(name: str, base: Path | None = None) -> Path:
    return context_dir(name, base) / "_current"


def _version_file(name: str, version: str, base: Path | None = None) -> Path:
    return context_dir(name, base) / f"{version}.yaml"


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
    d = context_dir(name, base)
    if not d.exists():
        return []
    versions = [f.stem for f in d.glob("v*.yaml")]
    versions.sort(key=_parse_version)
    return versions


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def save_context(
    name: str,
    template: str,
    slots: list[dict[str, Any]] | None = None,
    description: str = "",
    tags: list[str] | None = None,
    changelog: str = "",
    base: Path | None = None,
) -> tuple[str, bool]:
    """Save (or update) a context template. Returns (new_version, is_new_context)."""
    d = context_dir(name, base)
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
        "slots": slots or [],
        "template": template,
        "changelog": changelog,
    }

    with _version_file(name, new_version, base).open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    _current_file(name, base).write_text(new_version, encoding="utf-8")
    return new_version, is_new


def load_context(
    name: str,
    version: str | None = None,
    base: Path | None = None,
) -> dict[str, Any]:
    """Load a context by name (and optional version). Raises FileNotFoundError."""
    if version is None:
        version = get_current_version(name, base)
        if version is None:
            raise FileNotFoundError(f"Context '{name}' not found.")

    vf = _version_file(name, version, base)
    if not vf.exists():
        raise FileNotFoundError(f"Context '{name}@{version}' not found.")

    with vf.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_contexts(base: Path | None = None) -> list[dict[str, Any]]:
    """Return current version metadata for every context."""
    cd = contexts_dir(base)
    if not cd.exists():
        return []

    result = []
    for d in sorted(cd.iterdir()):
        if not d.is_dir():
            continue
        current = get_current_version(d.name, base)
        if current:
            try:
                result.append(load_context(d.name, current, base))
            except Exception:
                pass
    return result


def delete_context(
    name: str,
    version: str | None = None,
    base: Path | None = None,
) -> None:
    """Delete a context or a specific version of it."""
    d = context_dir(name, base)
    if not d.exists():
        raise FileNotFoundError(f"Context '{name}' not found.")

    if version is None:
        shutil.rmtree(d)
        return

    vf = _version_file(name, version, base)
    if not vf.exists():
        raise FileNotFoundError(f"Context '{name}@{version}' not found.")

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
# Render
# ---------------------------------------------------------------------------


def render_context(
    name: str,
    variables: dict[str, Any],
    version: str | None = None,
    base: Path | None = None,
) -> str:
    """Render a context template with provided variables.

    Applies default values for optional slots, raises ValueError for missing
    required slots.
    """
    data = load_context(name, version, base)
    slots: list[dict[str, Any]] = data.get("slots") or []
    template_str: str = data.get("template") or ""

    # Build the render context: start with defaults, then override with provided vars
    render_vars: dict[str, Any] = {}
    missing_required: list[str] = []

    for slot in slots:
        slot_name = slot["name"]
        required = slot.get("required", False)

        if slot_name in variables:
            render_vars[slot_name] = variables[slot_name]
        elif "default" in slot:
            render_vars[slot_name] = slot["default"]
        elif required:
            missing_required.append(slot_name)

    # Also pass through any extra variables not declared in slots
    for k, v in variables.items():
        if k not in render_vars:
            render_vars[k] = v

    if missing_required:
        raise ValueError(
            f"Missing required slot(s): {', '.join(missing_required)}"
        )

    try:
        from jinja2 import Environment, StrictUndefined, TemplateSyntaxError

        env = Environment(undefined=StrictUndefined)
        tmpl = env.from_string(template_str)
        return tmpl.render(**render_vars)
    except ImportError:
        # Fallback: simple string replacement for {{var}} patterns
        return _simple_render(template_str, render_vars)


def _simple_render(template: str, variables: dict[str, Any]) -> str:
    """Minimal Jinja2-style rendering fallback when jinja2 is not installed."""
    result = template
    for key, value in variables.items():
        result = result.replace("{{" + key + "}}", str(value))
        result = result.replace("{{ " + key + " }}", str(value))
    return result
