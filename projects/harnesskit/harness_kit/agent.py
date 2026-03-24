"""Agent asset management — data model and storage.

An Agent binds a Harness to a persistent identity and memory policy, enabling
interactive multi-turn conversations. Agents are stored without versioning
(latest definition always wins).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from harness_kit.config import harness_dir


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def agents_dir(base: Path | None = None) -> Path:
    return harness_dir(base) / "agents"


def _agent_file(name: str, base: Path | None = None) -> Path:
    return agents_dir(base) / f"{name}.yaml"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_agent_data(data: dict[str, Any]) -> list[str]:
    """Validate an agent dict. Returns a list of error strings (empty = valid)."""
    errors: list[str] = []

    if not data.get("name"):
        errors.append("'name' is required.")
    if not data.get("harness"):
        errors.append("'harness' is required.")

    # identity: if present, must be a dict
    identity = data.get("identity")
    if identity is not None and not isinstance(identity, dict):
        errors.append("'identity' must be a mapping with 'name' and 'description'.")

    # memory: if present, must be a dict with valid scope
    memory = data.get("memory")
    if memory is not None:
        if not isinstance(memory, dict):
            errors.append("'memory' must be a mapping.")
        else:
            scope = memory.get("scope")
            if scope and scope not in ("session", "harness", "global"):
                errors.append(
                    f"'memory.scope' must be 'session', 'harness', or 'global' (got '{scope}')."
                )

    # max_iterations: if present, must be a positive int
    mi = data.get("max_iterations")
    if mi is not None:
        try:
            if int(mi) <= 0:
                errors.append("'max_iterations' must be a positive integer.")
        except (TypeError, ValueError):
            errors.append("'max_iterations' must be an integer.")

    return errors


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def save_agent(
    name: str,
    harness_ref: str,
    identity_name: str = "",
    identity_description: str = "",
    memory_scope: str = "session",
    memory_persist: bool = False,
    max_iterations: int = 10,
    base: Path | None = None,
) -> bool:
    """Save (or overwrite) an agent definition.

    Returns True when a new agent was created, False when overwritten.
    """
    d = agents_dir(base)
    d.mkdir(parents=True, exist_ok=True)

    af = _agent_file(name, base)
    is_new = not af.exists()

    data: dict[str, Any] = {
        "name": name,
        "harness": harness_ref,
        "identity": {
            "name": identity_name or name,
            "description": identity_description,
        },
        "memory": {
            "scope": memory_scope,
            "persist": memory_persist,
        },
        "max_iterations": max_iterations,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    with af.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return is_new


def save_agent_from_dict(
    data: dict[str, Any],
    base: Path | None = None,
) -> bool:
    """Save an agent from a parsed YAML dict. Returns True when newly created."""
    name = data.get("name")
    if not name:
        raise ValueError("Agent YAML must have a 'name' field.")

    identity = data.get("identity") or {}
    memory = data.get("memory") or {}

    return save_agent(
        name=name,
        harness_ref=data.get("harness", ""),
        identity_name=identity.get("name", name),
        identity_description=identity.get("description", ""),
        memory_scope=memory.get("scope", "session"),
        memory_persist=bool(memory.get("persist", False)),
        max_iterations=int(data.get("max_iterations", 10)),
        base=base,
    )


def load_agent(
    name: str,
    base: Path | None = None,
) -> dict[str, Any]:
    """Load an agent by name. Raises FileNotFoundError if not found."""
    af = _agent_file(name, base)
    if not af.exists():
        raise FileNotFoundError(f"Agent '{name}' not found.")

    with af.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_agents(base: Path | None = None) -> list[dict[str, Any]]:
    """Return metadata for every agent."""
    ad = agents_dir(base)
    if not ad.exists():
        return []

    result = []
    for f in sorted(ad.glob("*.yaml")):
        try:
            result.append(yaml.safe_load(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return result


def delete_agent(name: str, base: Path | None = None) -> None:
    """Delete an agent definition."""
    af = _agent_file(name, base)
    if not af.exists():
        raise FileNotFoundError(f"Agent '{name}' not found.")
    af.unlink()


def validate_agent_references(
    name: str,
    base: Path | None = None,
) -> list[str]:
    """Check that the harness referenced by the agent exists.

    Returns a list of error strings (empty = all references valid).
    """
    from harness_kit import harness as _harness_mod

    errors: list[str] = []

    try:
        data = load_agent(name, base)
    except FileNotFoundError as e:
        return [str(e)]

    harness_ref = data.get("harness", "")
    if not harness_ref:
        errors.append("Agent has no 'harness' reference.")
        return errors

    # Parse name@version
    if "@" in harness_ref:
        h_name, h_version = harness_ref.split("@", 1)
    else:
        h_name, h_version = harness_ref, None

    try:
        _harness_mod.load_harness(h_name, h_version, base)
    except FileNotFoundError:
        errors.append(f"harness '{harness_ref}' not found.")

    return errors


# ---------------------------------------------------------------------------
# Conversation saving
# ---------------------------------------------------------------------------


def save_conversation(
    agent_name: str,
    memory_data: dict[str, Any],
    output_path: Path | None = None,
    base: Path | None = None,
) -> Path:
    """Persist a conversation snapshot to a JSON file.

    Saves to output_path when given, otherwise to
    `.harness/memory/conversations/{agent_name}-{timestamp}.json`.
    Returns the path written.
    """
    if output_path is None:
        conv_dir = harness_dir(base) / "memory" / "conversations"
        conv_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        output_path = conv_dir / f"{agent_name}-{ts}.json"

    snapshot = {
        "agent": agent_name,
        "saved_at": datetime.now(tz=timezone.utc).isoformat(),
        "turns": memory_data.get("turns", []),
        "metadata": memory_data.get("metadata", {}),
    }
    output_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path
