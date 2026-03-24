"""Harness asset management — data model and storage.

A Harness bundles multiple Skills together with model config, memory policy,
and global constraints, forming a complete runtime configuration for an Agent.
"""

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


def harnesses_dir(base: Path | None = None) -> Path:
    return harness_dir(base) / "harnesses"


def harness_asset_dir(name: str, base: Path | None = None) -> Path:
    return harnesses_dir(base) / name


def _current_file(name: str, base: Path | None = None) -> Path:
    return harness_asset_dir(name, base) / "_current"


def _version_file(name: str, version: str, base: Path | None = None) -> Path:
    return harness_asset_dir(name, base) / f"{version}.yaml"


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
    d = harness_asset_dir(name, base)
    if not d.exists():
        return []
    versions = [f.stem for f in d.glob("v*.yaml")]
    versions.sort(key=_parse_version)
    return versions


# ---------------------------------------------------------------------------
# Harness data model validation
# ---------------------------------------------------------------------------


def _validate_harness_data(data: dict[str, Any]) -> list[str]:
    """Validate a harness dict. Returns a list of error strings (empty = valid)."""
    errors: list[str] = []

    if not data.get("name"):
        errors.append("'name' is required.")
    if not data.get("description"):
        errors.append("'description' is required.")

    # skills: must be a list
    skills = data.get("skills")
    if skills is not None and not isinstance(skills, list):
        errors.append("'skills' must be a list of skill references.")

    # model: if present, must be a dict
    model = data.get("model")
    if model is not None and not isinstance(model, dict):
        errors.append("'model' must be a mapping (provider, name, temperature, ...).")

    # memory: if present, must be a dict with valid scope
    memory = data.get("memory")
    if memory is not None:
        if not isinstance(memory, dict):
            errors.append("'memory' must be a mapping.")
        else:
            scope = memory.get("scope")
            if scope and scope not in ("session", "harness", "global"):
                errors.append(
                    f"'memory.scope' must be one of 'session', 'harness', 'global' (got '{scope}')."
                )

    # constraints: if present, must be a dict
    constraints = data.get("constraints")
    if constraints is not None and not isinstance(constraints, dict):
        errors.append("'constraints' must be a mapping.")

    # context_budget: if present, must be a positive int
    budget = data.get("context_budget")
    if budget is not None:
        try:
            if int(budget) <= 0:
                errors.append("'context_budget' must be a positive integer.")
        except (TypeError, ValueError):
            errors.append("'context_budget' must be an integer.")

    return errors


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def save_harness(
    name: str,
    description: str = "",
    skills: list[str] | None = None,
    model: dict[str, Any] | None = None,
    memory: dict[str, Any] | None = None,
    constraints: dict[str, Any] | None = None,
    context_budget: int | None = None,
    changelog: str = "",
    base: Path | None = None,
) -> tuple[str, bool]:
    """Save (or update) a harness. Returns (new_version, is_new_harness)."""
    d = harness_asset_dir(name, base)
    d.mkdir(parents=True, exist_ok=True)

    current = get_current_version(name, base)
    is_new = current is None
    new_version = "v0.0.1" if is_new else _bump_patch(current)

    data: dict[str, Any] = {
        "name": name,
        "version": new_version,
        "description": description,
        "skills": skills or [],
        "model": model or {
            "provider": "openai",
            "name": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 2000,
        },
        "memory": memory or {
            "scope": "session",
            "max_turns": 10,
        },
        "constraints": constraints or {},
        "context_budget": context_budget or 4000,
        "changelog": changelog,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    with _version_file(name, new_version, base).open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    _current_file(name, base).write_text(new_version, encoding="utf-8")
    return new_version, is_new


def save_harness_from_dict(
    data: dict[str, Any],
    base: Path | None = None,
) -> tuple[str, bool]:
    """Save a harness from a parsed YAML dict (e.g. loaded from a file)."""
    name = data.get("name")
    if not name:
        raise ValueError("Harness YAML must have a 'name' field.")

    return save_harness(
        name=name,
        description=data.get("description", ""),
        skills=data.get("skills") or [],
        model=data.get("model"),
        memory=data.get("memory"),
        constraints=data.get("constraints"),
        context_budget=data.get("context_budget"),
        changelog=data.get("changelog", ""),
        base=base,
    )


def _is_version_string(s: str) -> bool:
    """Return True if s looks like a semantic version (v1.2.3)."""
    import re
    return bool(re.match(r"^v\d+\.\d+\.\d+$", s))


def load_harness(
    name: str,
    version: str | None = None,
    base: Path | None = None,
) -> dict[str, Any]:
    """Load a harness by name (and optional version). Raises FileNotFoundError."""
    if version is None:
        version = get_current_version(name, base)
        if version is None:
            raise FileNotFoundError(f"Harness '{name}' not found.")

    vf = _version_file(name, version, base)
    if not vf.exists():
        raise FileNotFoundError(f"Harness '{name}@{version}' not found.")

    with vf.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_harnesses(base: Path | None = None) -> list[dict[str, Any]]:
    """Return current-version metadata for every harness."""
    hd = harnesses_dir(base)
    if not hd.exists():
        return []

    result = []
    for d in sorted(hd.iterdir()):
        if not d.is_dir():
            continue
        current = get_current_version(d.name, base)
        if current:
            try:
                result.append(load_harness(d.name, current, base))
            except Exception:
                pass
    return result


def delete_harness(
    name: str,
    version: str | None = None,
    base: Path | None = None,
) -> None:
    """Delete a harness or a specific version of it."""
    d = harness_asset_dir(name, base)
    if not d.exists():
        raise FileNotFoundError(f"Harness '{name}' not found.")

    if version is None:
        shutil.rmtree(d)
        return

    vf = _version_file(name, version, base)
    if not vf.exists():
        raise FileNotFoundError(f"Harness '{name}@{version}' not found.")

    vf.unlink()

    # Re-point _current if we deleted the current version
    current = get_current_version(name, base)
    if current == version:
        remaining = list_versions(name, base)
        if remaining:
            _current_file(name, base).write_text(remaining[-1], encoding="utf-8")
        else:
            _current_file(name, base).unlink(missing_ok=True)


def diff_harnesses(
    name_a: str,
    version_a: str | None,
    name_b: str,
    version_b: str | None,
    base: Path | None = None,
) -> list[str]:
    """Return unified-diff lines between two harness versions (full YAML)."""
    import difflib

    data_a = load_harness(name_a, version_a, base)
    data_b = load_harness(name_b, version_b, base)

    label_a = f"{name_a}@{version_a or get_current_version(name_a, base)}"
    label_b = f"{name_b}@{version_b or get_current_version(name_b, base)}"

    text_a = yaml.dump(data_a, allow_unicode=True, default_flow_style=False, sort_keys=False)
    text_b = yaml.dump(data_b, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return list(
        difflib.unified_diff(
            text_a.splitlines(keepends=True),
            text_b.splitlines(keepends=True),
            fromfile=label_a,
            tofile=label_b,
        )
    )


def clone_harness(
    name: str,
    new_name: str,
    base: Path | None = None,
) -> str:
    """Clone a harness to a new name, resetting the version to v0.0.1.

    Returns the new version string ('v0.0.1').
    """
    if not harness_asset_dir(name, base).exists():
        raise FileNotFoundError(f"Harness '{name}' not found.")
    if harness_asset_dir(new_name, base).exists():
        raise FileExistsError(f"Harness '{new_name}' already exists.")

    data = load_harness(name, base=base)

    # Reset identity fields
    data["name"] = new_name
    data["version"] = "v0.0.1"
    data["changelog"] = f"Cloned from '{name}'"
    data["created_at"] = datetime.now(tz=timezone.utc).isoformat()

    d = harness_asset_dir(new_name, base)
    d.mkdir(parents=True, exist_ok=True)

    with _version_file(new_name, "v0.0.1", base).open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    _current_file(new_name, base).write_text("v0.0.1", encoding="utf-8")
    return "v0.0.1"


# ---------------------------------------------------------------------------
# Skill reference validation
# ---------------------------------------------------------------------------


def _parse_skill_ref(ref: str) -> tuple[str, str | None]:
    """'name@version' -> ('name', 'version'). 'name' -> ('name', None)."""
    if "@" in ref:
        parts = ref.split("@", 1)
        return parts[0], parts[1]
    return ref, None


def validate_harness_references(
    name: str,
    version: str | None = None,
    base: Path | None = None,
) -> list[str]:
    """Check that all skill references in a harness are resolvable.

    Returns a list of error strings (empty = all references valid).
    """
    from harness_kit import skill as _skill_mod

    errors: list[str] = []

    try:
        data = load_harness(name, version, base)
    except FileNotFoundError as e:
        return [str(e)]

    skills = data.get("skills") or []
    for ref in skills:
        sname, sver = _parse_skill_ref(str(ref))
        try:
            _skill_mod.load_skill(sname, sver, base)
        except FileNotFoundError:
            errors.append(f"skill '{ref}' not found.")

    # Validate constraint rules if specified
    constraints = data.get("constraints") or {}
    constraint_rules = constraints.get("rules") or []
    if isinstance(constraint_rules, list):
        from harness_kit import rule as _rule_mod
        for rule_name in constraint_rules:
            rf = _rule_mod._rule_file(str(rule_name), base)
            if not rf.exists():
                errors.append(f"constraints.rules: '{rule_name}' not found.")

    return errors
