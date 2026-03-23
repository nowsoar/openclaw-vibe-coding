"""Skill asset management — data model and storage."""

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


def skills_dir(base: Path | None = None) -> Path:
    return harness_dir(base) / "skills"


def skill_dir(name: str, base: Path | None = None) -> Path:
    return skills_dir(base) / name


def _current_file(name: str, base: Path | None = None) -> Path:
    return skill_dir(name, base) / "_current"


def _version_file(name: str, version: str, base: Path | None = None) -> Path:
    return skill_dir(name, base) / f"{version}.yaml"


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
    d = skill_dir(name, base)
    if not d.exists():
        return []
    versions = [f.stem for f in d.glob("v*.yaml")]
    versions.sort(key=_parse_version)
    return versions


# ---------------------------------------------------------------------------
# Skill data model validation
# ---------------------------------------------------------------------------


def _validate_skill_data(data: dict[str, Any]) -> list[str]:
    """Validate a skill dict. Returns a list of error strings (empty = valid)."""
    errors: list[str] = []

    if not data.get("name"):
        errors.append("'name' is required.")
    if not data.get("description"):
        errors.append("'description' is required.")

    # inputs: each entry must have 'name' and 'type'
    for i, inp in enumerate(data.get("inputs") or []):
        if not isinstance(inp, dict):
            errors.append(f"inputs[{i}] must be a mapping.")
            continue
        if not inp.get("name"):
            errors.append(f"inputs[{i}] missing 'name'.")
        if not inp.get("type"):
            errors.append(f"inputs[{i}] missing 'type'.")

    # outputs: each entry must have 'name' and 'type'
    for i, out in enumerate(data.get("outputs") or []):
        if not isinstance(out, dict):
            errors.append(f"outputs[{i}] must be a mapping.")
            continue
        if not out.get("name"):
            errors.append(f"outputs[{i}] missing 'name'.")
        if not out.get("type"):
            errors.append(f"outputs[{i}] missing 'type'.")

    return errors


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def save_skill(
    name: str,
    description: str = "",
    trigger: str = "",
    inputs: list[dict[str, Any]] | None = None,
    outputs: list[dict[str, Any]] | None = None,
    assets: dict[str, Any] | None = None,
    examples: list[dict[str, Any]] | None = None,
    changelog: str = "",
    base: Path | None = None,
) -> tuple[str, bool]:
    """Save (or update) a skill. Returns (new_version, is_new_skill)."""
    d = skill_dir(name, base)
    d.mkdir(parents=True, exist_ok=True)

    current = get_current_version(name, base)
    is_new = current is None
    new_version = "v0.0.1" if is_new else _bump_patch(current)

    data: dict[str, Any] = {
        "name": name,
        "version": new_version,
        "description": description,
        "trigger": trigger,
        "inputs": inputs or [],
        "outputs": outputs or [],
        "assets": assets or {},
        "examples": examples or [],
        "changelog": changelog,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    with _version_file(name, new_version, base).open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    _current_file(name, base).write_text(new_version, encoding="utf-8")
    return new_version, is_new


def save_skill_from_dict(
    data: dict[str, Any],
    base: Path | None = None,
) -> tuple[str, bool]:
    """Save a skill from a parsed YAML dict (e.g. loaded from a file)."""
    name = data.get("name")
    if not name:
        raise ValueError("Skill YAML must have a 'name' field.")

    return save_skill(
        name=name,
        description=data.get("description", ""),
        trigger=data.get("trigger", ""),
        inputs=data.get("inputs") or [],
        outputs=data.get("outputs") or [],
        assets=data.get("assets") or {},
        examples=data.get("examples") or [],
        changelog=data.get("changelog", ""),
        base=base,
    )


def load_skill(
    name: str,
    version: str | None = None,
    base: Path | None = None,
) -> dict[str, Any]:
    """Load a skill by name (and optional version). Raises FileNotFoundError."""
    if version is None:
        version = get_current_version(name, base)
        if version is None:
            raise FileNotFoundError(f"Skill '{name}' not found.")

    vf = _version_file(name, version, base)
    if not vf.exists():
        raise FileNotFoundError(f"Skill '{name}@{version}' not found.")

    with vf.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_skills(base: Path | None = None) -> list[dict[str, Any]]:
    """Return current-version metadata for every skill."""
    sd = skills_dir(base)
    if not sd.exists():
        return []

    result = []
    for d in sorted(sd.iterdir()):
        if not d.is_dir():
            continue
        current = get_current_version(d.name, base)
        if current:
            try:
                result.append(load_skill(d.name, current, base))
            except Exception:
                pass
    return result


def delete_skill(
    name: str,
    version: str | None = None,
    base: Path | None = None,
) -> None:
    """Delete a skill or a specific version of it."""
    d = skill_dir(name, base)
    if not d.exists():
        raise FileNotFoundError(f"Skill '{name}' not found.")

    if version is None:
        shutil.rmtree(d)
        return

    vf = _version_file(name, version, base)
    if not vf.exists():
        raise FileNotFoundError(f"Skill '{name}@{version}' not found.")

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
# Asset reference helpers (Phase 2.2)
# ---------------------------------------------------------------------------


def _parse_asset_ref(ref: str) -> tuple[str, str | None]:
    """'name@version' -> ('name', 'version'). 'name' -> ('name', None)."""
    if "@" in ref:
        parts = ref.split("@", 1)
        return parts[0], parts[1]
    return ref, None


def diff_skills(
    name_a: str,
    version_a: str | None,
    name_b: str,
    version_b: str | None,
    base: Path | None = None,
) -> list[str]:
    """Return unified-diff lines between two skill versions (full YAML)."""
    import difflib

    data_a = load_skill(name_a, version_a, base)
    data_b = load_skill(name_b, version_b, base)

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


def validate_skill_references(
    name: str,
    version: str | None = None,
    base: Path | None = None,
) -> list[str]:
    """Check that all asset references in a skill are resolvable.

    Returns a list of error strings (empty = all references valid).
    """
    from harness_kit import prompt as _prompt_mod
    from harness_kit import schema as _schema_mod
    from harness_kit import rule as _rule_mod
    from harness_kit import context as _context_mod

    errors: list[str] = []

    try:
        data = load_skill(name, version, base)
    except FileNotFoundError as e:
        return [str(e)]

    assets = data.get("assets") or {}

    # Check prompt references
    prompts = assets.get("prompts") or {}
    if isinstance(prompts, dict):
        for role, ref in prompts.items():
            if not ref:
                continue
            pname, pver = _parse_asset_ref(str(ref))
            try:
                _prompt_mod.load_prompt(pname, pver, base)
            except FileNotFoundError:
                errors.append(f"prompts.{role}: '{ref}' not found.")

    # Check schema references
    schemas = assets.get("schemas") or []
    if isinstance(schemas, list):
        for ref in schemas:
            sname, sver = _parse_asset_ref(str(ref))
            try:
                _schema_mod.load_schema(sname, sver, base)
            except FileNotFoundError:
                errors.append(f"schemas: '{ref}' not found.")

    # Check rule references (rules have no versioning)
    rules = assets.get("rules") or []
    if isinstance(rules, list):
        for ref in rules:
            rname, _ = _parse_asset_ref(str(ref))
            rf = _rule_mod._rule_file(rname, base)
            if not rf.exists():
                errors.append(f"rules: '{ref}' not found.")

    # Check context reference
    context_ref = assets.get("context")
    if context_ref:
        cname, cver = _parse_asset_ref(str(context_ref))
        try:
            _context_mod.load_context(cname, cver, base)
        except FileNotFoundError:
            errors.append(f"context: '{context_ref}' not found.")

    return errors


def render_skill_prompt(
    name: str,
    version: str | None = None,
    base: Path | None = None,
) -> dict[str, str]:
    """Resolve all asset references and return rendered content.

    Returns a dict with keys: 'system', 'user', 'context', 'rules', 'schemas'.
    Values are the resolved content strings (empty string if not present).
    """
    from harness_kit import prompt as _prompt_mod
    from harness_kit import schema as _schema_mod
    from harness_kit import rule as _rule_mod
    from harness_kit import context as _context_mod

    data = load_skill(name, version, base)
    assets = data.get("assets") or {}
    result: dict[str, str] = {
        "system": "",
        "user": "",
        "context": "",
        "rules": "",
        "schemas": "",
    }

    # Resolve prompt references
    prompts = assets.get("prompts") or {}
    if isinstance(prompts, dict):
        for role in ("system", "user"):
            ref = prompts.get(role)
            if ref:
                pname, pver = _parse_asset_ref(str(ref))
                try:
                    pdata = _prompt_mod.load_prompt(pname, pver, base)
                    result[role] = pdata.get("content", "")
                except FileNotFoundError:
                    result[role] = f"[ERROR: '{ref}' not found]"

    # Resolve context reference
    context_ref = assets.get("context")
    if context_ref:
        cname, cver = _parse_asset_ref(str(context_ref))
        try:
            cdata = _context_mod.load_context(cname, cver, base)
            result["context"] = cdata.get("template", "")
        except FileNotFoundError:
            result["context"] = f"[ERROR: '{context_ref}' not found]"

    # Collect rule descriptions
    rules = assets.get("rules") or []
    rule_lines = []
    for ref in (rules if isinstance(rules, list) else []):
        rname, _ = _parse_asset_ref(str(ref))
        rf = _rule_mod._rule_file(rname, base)
        if rf.exists():
            try:
                rdata = yaml.safe_load(rf.read_text(encoding="utf-8"))
                rule_lines.append(
                    f"[{rdata.get('type', '?')}] {rname}: {rdata.get('description', '')}"
                )
            except Exception:
                rule_lines.append(f"[?] {rname}")
        else:
            rule_lines.append(f"[ERROR: '{ref}' not found]")
    result["rules"] = "\n".join(rule_lines)

    # Collect schema names/refs
    schemas = assets.get("schemas") or []
    schema_lines = []
    for ref in (schemas if isinstance(schemas, list) else []):
        sname, sver = _parse_asset_ref(str(ref))
        try:
            sdata = _schema_mod.load_schema(sname, sver, base)
            schema_lines.append(f"{sname}: {sdata.get('description', '')}")
        except FileNotFoundError:
            schema_lines.append(f"[ERROR: '{ref}' not found]")
    result["schemas"] = "\n".join(schema_lines)

    return result
