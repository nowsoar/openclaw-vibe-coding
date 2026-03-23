"""Prompt asset management — data model and storage."""

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


def prompts_dir(base: Path | None = None) -> Path:
    return harness_dir(base) / "prompts"


def prompt_dir(name: str, base: Path | None = None) -> Path:
    return prompts_dir(base) / name


def _current_file(name: str, base: Path | None = None) -> Path:
    return prompt_dir(name, base) / "_current"


def _version_file(name: str, version: str, base: Path | None = None) -> Path:
    return prompt_dir(name, base) / f"{version}.yaml"


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
    d = prompt_dir(name, base)
    if not d.exists():
        return []
    versions = [f.stem for f in d.glob("v*.yaml")]
    versions.sort(key=_parse_version)
    return versions


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def save_prompt(
    name: str,
    content: str,
    description: str = "",
    tags: list[str] | None = None,
    variables: list[dict[str, Any]] | None = None,
    changelog: str = "",
    base: Path | None = None,
) -> tuple[str, bool]:
    """Save (or update) a prompt. Returns (new_version, is_new_prompt)."""
    d = prompt_dir(name, base)
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
        "variables": variables or [],
        "content": content,
        "changelog": changelog,
    }

    with _version_file(name, new_version, base).open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    _current_file(name, base).write_text(new_version, encoding="utf-8")
    return new_version, is_new


def load_prompt(
    name: str,
    version: str | None = None,
    base: Path | None = None,
) -> dict[str, Any]:
    """Load a prompt by name (and optional version). Raises FileNotFoundError."""
    if version is None:
        version = get_current_version(name, base)
        if version is None:
            raise FileNotFoundError(f"Prompt '{name}' not found.")

    vf = _version_file(name, version, base)
    if not vf.exists():
        raise FileNotFoundError(f"Prompt '{name}@{version}' not found.")

    with vf.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_prompts(base: Path | None = None) -> list[dict[str, Any]]:
    """Return current version metadata for every prompt."""
    pd = prompts_dir(base)
    if not pd.exists():
        return []

    result = []
    for d in sorted(pd.iterdir()):
        if not d.is_dir():
            continue
        current = get_current_version(d.name, base)
        if current:
            try:
                result.append(load_prompt(d.name, current, base))
            except Exception:
                pass
    return result


def delete_prompt(
    name: str,
    version: str | None = None,
    base: Path | None = None,
) -> None:
    """Delete a prompt or a specific version of it."""
    d = prompt_dir(name, base)
    if not d.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found.")

    if version is None:
        shutil.rmtree(d)
        return

    vf = _version_file(name, version, base)
    if not vf.exists():
        raise FileNotFoundError(f"Prompt '{name}@{version}' not found.")

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
# Diff helper
# ---------------------------------------------------------------------------


def diff_prompts(
    name_a: str,
    version_a: str | None,
    name_b: str,
    version_b: str | None,
    base: Path | None = None,
) -> list[str]:
    """Return unified-diff lines between two prompt versions."""
    import difflib

    data_a = load_prompt(name_a, version_a, base)
    data_b = load_prompt(name_b, version_b, base)

    label_a = f"{name_a}@{version_a or get_current_version(name_a, base)}"
    label_b = f"{name_b}@{version_b or get_current_version(name_b, base)}"

    lines_a = data_a.get("content", "").splitlines(keepends=True)
    lines_b = data_b.get("content", "").splitlines(keepends=True)

    return list(
        difflib.unified_diff(lines_a, lines_b, fromfile=label_a, tofile=label_b)
    )
