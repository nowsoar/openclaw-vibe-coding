"""Skills Registry — local index at ~/.harnesskit/registry.json."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Registry paths
# ---------------------------------------------------------------------------


def _registry_dir() -> Path:
    return Path.home() / ".harnesskit"


def _registry_file() -> Path:
    return _registry_dir() / "registry.json"


# ---------------------------------------------------------------------------
# Low-level I/O
# ---------------------------------------------------------------------------


def _load_registry() -> dict[str, Any]:
    f = _registry_file()
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _log.warning("Registry file %s is corrupted (invalid JSON); starting with empty registry.", f)
        return {}


def _save_registry(data: dict[str, Any]) -> None:
    d = _registry_dir()
    d.mkdir(parents=True, exist_ok=True)
    _registry_file().write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def register_skill(
    name: str,
    version: str,
    source: str,
    description: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Add or update a skill entry in the local registry."""
    data = _load_registry()
    entry: dict[str, Any] = {
        "name": name,
        "version": version,
        "source": source,
        "description": description,
        "tags": tags or [],
        "installed_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    data[name] = entry
    _save_registry(data)
    return entry


def unregister_skill(name: str) -> bool:
    """Remove a skill from the local registry. Returns True if it existed."""
    data = _load_registry()
    if name in data:
        del data[name]
        _save_registry(data)
        return True
    return False


def list_registry() -> list[dict[str, Any]]:
    """Return all entries in the local registry, sorted by name."""
    data = _load_registry()
    return sorted(data.values(), key=lambda e: e["name"])


def get_registry_entry(name: str) -> dict[str, Any] | None:
    """Return a single registry entry or None."""
    return _load_registry().get(name)


def search_registry(keyword: str) -> list[dict[str, Any]]:
    """Search local registry entries by name, description, or tags (case-insensitive)."""
    kw = keyword.lower()
    results = []
    for entry in list_registry():
        if (
            kw in entry.get("name", "").lower()
            or kw in entry.get("description", "").lower()
            or any(kw in t.lower() for t in entry.get("tags", []))
        ):
            results.append(entry)
    return results
