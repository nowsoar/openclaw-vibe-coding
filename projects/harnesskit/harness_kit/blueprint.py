"""Blueprint asset management — data model and storage.

A Blueprint defines a deterministic + agentic mixed workflow, where each step
is either a shell command (deterministic) or a Harness/Skill call (agentic).
Steps can pass data to each other via ``{{steps.xxx.output}}`` interpolation.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from harness_kit.config import harness_dir


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def blueprints_dir(base: Path | None = None) -> Path:
    return harness_dir(base) / "blueprints"


def blueprint_asset_dir(name: str, base: Path | None = None) -> Path:
    return blueprints_dir(base) / name


def _current_file(name: str, base: Path | None = None) -> Path:
    return blueprint_asset_dir(name, base) / "_current"


def _version_file(name: str, version: str, base: Path | None = None) -> Path:
    return blueprint_asset_dir(name, base) / f"{version}.yaml"


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
    d = blueprint_asset_dir(name, base)
    if not d.exists():
        return []
    versions = [f.stem for f in d.glob("v*.yaml")]
    versions.sort(key=_parse_version)
    return versions


# ---------------------------------------------------------------------------
# Blueprint data model validation
# ---------------------------------------------------------------------------

_VALID_STEP_TYPES = ("deterministic", "agentic")
_VALID_ON_FAIL = ("stop", "continue")
_VAR_PATTERN = re.compile(r"\{\{[^}]+\}\}")


def _validate_blueprint_data(data: dict[str, Any]) -> list[str]:
    """Validate a blueprint dict. Returns a list of error strings (empty = valid)."""
    errors: list[str] = []

    if not data.get("name"):
        errors.append("'name' is required.")
    if not data.get("description"):
        errors.append("'description' is required.")

    # inputs: optional, must be a list of dicts with 'name'
    inputs = data.get("inputs")
    if inputs is not None:
        if not isinstance(inputs, list):
            errors.append("'inputs' must be a list.")
        else:
            for i, inp in enumerate(inputs):
                if not isinstance(inp, dict):
                    errors.append(f"'inputs[{i}]' must be a mapping.")
                elif not inp.get("name"):
                    errors.append(f"'inputs[{i}].name' is required.")

    # steps: required, non-empty list
    steps = data.get("steps")
    if not steps:
        errors.append("'steps' must be a non-empty list.")
    elif not isinstance(steps, list):
        errors.append("'steps' must be a list.")
    else:
        step_ids: set[str] = set()
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                errors.append(f"'steps[{i}]' must be a mapping.")
                continue

            step_id = step.get("id")
            if not step_id:
                errors.append(f"'steps[{i}].id' is required.")
            elif step_id in step_ids:
                errors.append(f"Duplicate step id '{step_id}'.")
            else:
                step_ids.add(str(step_id))

            step_type = step.get("type")
            if not step_type:
                errors.append(f"'steps[{i}].type' is required.")
            elif step_type not in _VALID_STEP_TYPES:
                errors.append(
                    f"'steps[{i}].type' must be one of {_VALID_STEP_TYPES} "
                    f"(got '{step_type}')."
                )

            if step_type == "deterministic" and not step.get("run"):
                errors.append(
                    f"'steps[{i}]' (deterministic) must have a 'run' command."
                )
            if step_type == "agentic" and not (step.get("harness") or step.get("skill")):
                errors.append(
                    f"'steps[{i}]' (agentic) must have 'harness' or 'skill'."
                )

            on_fail = step.get("on_fail")
            if on_fail and not (
                on_fail in _VALID_ON_FAIL or str(on_fail).startswith("goto:")
            ):
                errors.append(
                    f"'steps[{i}].on_fail' must be 'stop', 'continue', or 'goto:<id>'."
                )

            timeout = step.get("timeout")
            if timeout is not None:
                try:
                    if int(timeout) <= 0:
                        errors.append(f"'steps[{i}].timeout' must be a positive integer.")
                except (TypeError, ValueError):
                    errors.append(f"'steps[{i}].timeout' must be an integer.")

    # outputs: optional, must be a dict
    outputs = data.get("outputs")
    if outputs is not None and not isinstance(outputs, dict):
        errors.append("'outputs' must be a mapping.")

    return errors


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def save_blueprint(
    name: str,
    description: str = "",
    inputs: list[dict[str, Any]] | None = None,
    steps: list[dict[str, Any]] | None = None,
    outputs: dict[str, Any] | None = None,
    changelog: str = "",
    base: Path | None = None,
) -> tuple[str, bool]:
    """Save (or update) a blueprint. Returns (new_version, is_new_blueprint)."""
    d = blueprint_asset_dir(name, base)
    d.mkdir(parents=True, exist_ok=True)

    current = get_current_version(name, base)
    is_new = current is None
    new_version = "v0.0.1" if is_new else _bump_patch(current)

    data: dict[str, Any] = {
        "name": name,
        "version": new_version,
        "description": description,
        "inputs": inputs or [],
        "steps": steps or [],
        "outputs": outputs or {},
        "changelog": changelog,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    with _version_file(name, new_version, base).open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    _current_file(name, base).write_text(new_version, encoding="utf-8")
    return new_version, is_new


def save_blueprint_from_dict(
    data: dict[str, Any],
    base: Path | None = None,
) -> tuple[str, bool]:
    """Save a blueprint from a parsed YAML dict (e.g. loaded from a file)."""
    name = data.get("name")
    if not name:
        raise ValueError("Blueprint YAML must have a 'name' field.")

    return save_blueprint(
        name=name,
        description=data.get("description", ""),
        inputs=data.get("inputs") or [],
        steps=data.get("steps") or [],
        outputs=data.get("outputs") or {},
        changelog=data.get("changelog", ""),
        base=base,
    )


def load_blueprint(
    name: str,
    version: str | None = None,
    base: Path | None = None,
) -> dict[str, Any]:
    """Load a blueprint by name (and optional version). Raises FileNotFoundError."""
    if version is None:
        version = get_current_version(name, base)
        if version is None:
            raise FileNotFoundError(f"Blueprint '{name}' not found.")

    vf = _version_file(name, version, base)
    if not vf.exists():
        raise FileNotFoundError(f"Blueprint '{name}@{version}' not found.")

    with vf.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_blueprints(base: Path | None = None) -> list[dict[str, Any]]:
    """Return current-version metadata for every blueprint."""
    bd = blueprints_dir(base)
    if not bd.exists():
        return []

    result = []
    for d in sorted(bd.iterdir()):
        if not d.is_dir():
            continue
        current = get_current_version(d.name, base)
        if current:
            try:
                result.append(load_blueprint(d.name, current, base))
            except Exception:
                pass
    return result


def delete_blueprint(
    name: str,
    version: str | None = None,
    base: Path | None = None,
) -> None:
    """Delete a blueprint or a specific version of it."""
    d = blueprint_asset_dir(name, base)
    if not d.exists():
        raise FileNotFoundError(f"Blueprint '{name}' not found.")

    if version is None:
        shutil.rmtree(d)
        return

    vf = _version_file(name, version, base)
    if not vf.exists():
        raise FileNotFoundError(f"Blueprint '{name}@{version}' not found.")

    vf.unlink()

    # Re-point _current if we deleted the current version
    current = get_current_version(name, base)
    if current == version:
        remaining = list_versions(name, base)
        if remaining:
            _current_file(name, base).write_text(remaining[-1], encoding="utf-8")
        else:
            _current_file(name, base).unlink(missing_ok=True)


def diff_blueprints(
    name_a: str,
    version_a: str | None,
    name_b: str,
    version_b: str | None,
    base: Path | None = None,
) -> list[str]:
    """Return unified-diff lines between two blueprint versions (full YAML)."""
    import difflib

    data_a = load_blueprint(name_a, version_a, base)
    data_b = load_blueprint(name_b, version_b, base)

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


# ---------------------------------------------------------------------------
# Variable interpolation validation
# ---------------------------------------------------------------------------


def extract_variable_refs(data: dict[str, Any]) -> list[str]:
    """Extract all ``{{...}}`` variable references from a blueprint YAML dump."""
    text = yaml.dump(data, allow_unicode=True, default_flow_style=False)
    return _VAR_PATTERN.findall(text)


def validate_variable_refs(data: dict[str, Any]) -> list[str]:
    """Check that all ``{{steps.xxx.yyy}}`` references point to declared step IDs.

    Returns a list of error strings (empty = valid).
    """
    errors: list[str] = []
    steps = data.get("steps") or []
    step_ids = {str(s.get("id", "")) for s in steps if isinstance(s, dict)}
    input_names = {
        str(inp.get("name", "")) for inp in (data.get("inputs") or []) if isinstance(inp, dict)
    }

    for ref in extract_variable_refs(data):
        inner = ref[2:-2].strip()  # strip {{ }}
        if inner.startswith("steps."):
            parts = inner.split(".")
            if len(parts) >= 2:
                sid = parts[1]
                if sid not in step_ids:
                    errors.append(
                        f"Variable '{{{{ {inner} }}}}' references unknown step '{sid}'."
                    )
        elif inner.startswith("inputs."):
            parts = inner.split(".")
            if len(parts) >= 2:
                iname = parts[1]
                if iname not in input_names:
                    errors.append(
                        f"Variable '{{{{ {inner} }}}}' references unknown input '{iname}'."
                    )
    return errors


# ---------------------------------------------------------------------------
# Phase 4.2: Enhanced static validation
# ---------------------------------------------------------------------------


def _parse_asset_ref(ref: str) -> tuple[str, str | None]:
    """Parse 'name@version' into (name, version). Version is None if unspecified."""
    if "@" in ref:
        name, version = ref.split("@", 1)
        return name.strip(), version.strip()
    return ref.strip(), None


def validate_asset_refs(data: dict[str, Any], base: Path | None = None) -> list[str]:
    """Check that all harness/skill references in agentic steps exist on disk.

    Returns a list of error strings (empty = all refs valid).
    """
    from harness_kit import harness as harness_mod  # avoid top-level circular import
    from harness_kit import skill as skill_mod

    errors: list[str] = []
    steps = data.get("steps") or []

    for step in steps:
        if not isinstance(step, dict) or step.get("type") != "agentic":
            continue
        step_id = step.get("id", "?")

        harness_ref = step.get("harness")
        if harness_ref:
            h_name, h_version = _parse_asset_ref(str(harness_ref))
            if h_version:
                vf = harness_mod.harness_asset_dir(h_name, base) / f"{h_version}.yaml"
                if not vf.exists():
                    errors.append(
                        f"Step '{step_id}': harness '{harness_ref}' not found. "
                        f"Fix: run 'harnesskit harness list' to see available harnesses."
                    )
            else:
                current = harness_mod.get_current_version(h_name, base)
                if current is None:
                    errors.append(
                        f"Step '{step_id}': harness '{h_name}' not found. "
                        f"Fix: create it with 'harnesskit harness create {h_name}'."
                    )

        skill_ref = step.get("skill")
        if skill_ref:
            s_name, s_version = _parse_asset_ref(str(skill_ref))
            if s_version:
                vf = skill_mod.skill_dir(s_name, base) / f"{s_version}.yaml"
                if not vf.exists():
                    errors.append(
                        f"Step '{step_id}': skill '{skill_ref}' not found. "
                        f"Fix: run 'harnesskit skill list' to see available skills."
                    )
            else:
                current = skill_mod.get_current_version(s_name, base)
                if current is None:
                    errors.append(
                        f"Step '{step_id}': skill '{s_name}' not found. "
                        f"Fix: create it with 'harnesskit skill save --file <yaml>'."
                    )

    return errors


def validate_goto_targets(data: dict[str, Any]) -> list[str]:
    """Check that all ``goto:<id>`` on_fail values reference valid step IDs.

    Returns a list of error strings (empty = valid).
    """
    errors: list[str] = []
    steps = data.get("steps") or []
    if not isinstance(steps, list):
        return errors

    step_ids = {
        str(s.get("id", ""))
        for s in steps
        if isinstance(s, dict) and s.get("id")
    }

    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = step.get("id", "?")
        on_fail = str(step.get("on_fail", ""))
        if on_fail.startswith("goto:"):
            target = on_fail[5:]
            if target not in step_ids:
                hints = ", ".join(f"'{sid}'" for sid in sorted(step_ids))
                errors.append(
                    f"Step '{step_id}': on_fail='goto:{target}' references unknown step. "
                    f"Fix: use one of: {hints}."
                )

    return errors


def detect_variable_cycles(data: dict[str, Any]) -> list[str]:
    """Detect circular variable dependencies between steps.

    E.g. step A uses ``{{steps.B.output}}`` and step B uses ``{{steps.A.output}}``.
    Returns a list of error strings (empty = no cycles).
    """
    errors: list[str] = []
    steps = data.get("steps") or []
    if not isinstance(steps, list):
        return errors

    # Build dependency graph: step_id → set of step_ids it references
    step_ids: set[str] = set()
    for step in steps:
        if isinstance(step, dict) and step.get("id"):
            step_ids.add(str(step["id"]))

    step_deps: dict[str, set[str]] = {}
    for step in steps:
        if not isinstance(step, dict):
            continue
        sid = str(step.get("id", ""))
        if not sid:
            continue
        step_text = yaml.dump(step, allow_unicode=True)
        refs = set(re.findall(r"\{\{steps\.([^.}\s]+)\.[^}]+\}\}", step_text))
        step_deps[sid] = refs & step_ids  # only edges to known steps

    # DFS cycle detection (white/gray/black colouring)
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {sid: WHITE for sid in step_ids}
    reported: set[str] = set()

    def dfs(node: str, path: list[str]) -> None:
        color[node] = GRAY
        for dep in step_deps.get(node, set()):
            if color.get(dep) == GRAY:
                # Cycle found — extract the cycle portion of the path
                try:
                    cycle_start = path.index(dep)
                except ValueError:
                    cycle_start = 0
                cycle = path[cycle_start:] + [dep]
                cycle_key = "→".join(cycle)
                if cycle_key not in reported:
                    reported.add(cycle_key)
                    errors.append(
                        f"Circular variable dependency detected: {cycle_key}. "
                        "Fix: reorder steps or remove the circular reference."
                    )
            elif color.get(dep, WHITE) == WHITE:
                dfs(dep, path + [dep])
        color[node] = BLACK

    for sid in list(step_ids):
        if color[sid] == WHITE:
            dfs(sid, [sid])

    return errors


def full_validate(
    data: dict[str, Any],
    base: Path | None = None,
) -> dict[str, list[str]]:
    """Run all Blueprint validation checks and return results grouped by category.

    Returns a dict ``{category: [error, ...]}``.  An empty list means no errors
    for that category.
    """
    return {
        "structure": _validate_blueprint_data(data),
        "variable_refs": validate_variable_refs(data),
        "asset_refs": validate_asset_refs(data, base),
        "goto_targets": validate_goto_targets(data),
        "variable_cycles": detect_variable_cycles(data),
    }
