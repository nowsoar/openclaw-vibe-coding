"""Asset reference resolution and dependency checking for HarnessKit."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from harness_kit.config import harness_dir

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEMVER_RE = re.compile(r"^v\d+\.\d+\.\d+$")
VERSIONED_ASSET_TYPES = ("prompt", "schema", "context")
ALL_ASSET_TYPES = ("prompt", "schema", "context", "rule")

# Directories that may contain definitions referencing primitive assets
CONSUMER_SUBDIRS = ("skills", "harnesses", "agents", "blueprints")


# ---------------------------------------------------------------------------
# Reference model
# ---------------------------------------------------------------------------


@dataclass
class AssetRef:
    """Parsed asset reference."""

    name: str
    version: str | None  # semver like "v0.1.0" — exact version (mutually exclusive with tag)
    tag: str | None      # tag alias like "production" (mutually exclusive with version)
    raw: str             # original reference string

    @property
    def ref_kind(self) -> str:
        """Return 'exact', 'tag', or 'current'."""
        if self.version:
            return "exact"
        if self.tag:
            return "tag"
        return "current"


def parse_ref(ref: str) -> AssetRef:
    """Parse a reference string into an AssetRef.

    Supported formats:
      - ``name@v0.1.0``   → exact semver version
      - ``name@production`` → tag alias
      - ``name``          → current version
    """
    if "@" in ref:
        name, qualifier = ref.rsplit("@", 1)
        if SEMVER_RE.match(qualifier):
            return AssetRef(name=name, version=qualifier, tag=None, raw=ref)
        return AssetRef(name=name, version=None, tag=qualifier, raw=ref)
    return AssetRef(name=ref, version=None, tag=None, raw=ref)


# ---------------------------------------------------------------------------
# Tag storage helpers
# ---------------------------------------------------------------------------


def _tags_dir(asset_type: str, name: str, base: Path | None = None) -> Path:
    """Return the ``_tags/`` directory for a versioned asset."""
    hd = harness_dir(base)
    return hd / f"{asset_type}s" / name / "_tags"


def set_tag(
    asset_type: str,
    name: str,
    tag: str,
    version: str,
    base: Path | None = None,
) -> None:
    """Create or update a tag alias for a versioned asset.

    Args:
        asset_type: One of ``"prompt"``, ``"schema"``, ``"context"``.
        name: Asset name.
        tag: Tag name (e.g. ``"production"``).
        version: Version string the tag should point to (e.g. ``"v0.1.0"``).
        base: Optional workspace root (defaults to CWD).

    Raises:
        ValueError: If ``asset_type`` does not support tags.
    """
    if asset_type not in VERSIONED_ASSET_TYPES:
        raise ValueError(
            f"Tags are only supported for versioned assets: {VERSIONED_ASSET_TYPES}"
        )
    td = _tags_dir(asset_type, name, base)
    td.mkdir(parents=True, exist_ok=True)
    (td / tag).write_text(version, encoding="utf-8")


def get_tag_version(
    asset_type: str,
    name: str,
    tag: str,
    base: Path | None = None,
) -> str | None:
    """Return the version a tag points to, or ``None`` if not found."""
    tf = _tags_dir(asset_type, name, base) / tag
    return tf.read_text(encoding="utf-8").strip() if tf.exists() else None


def list_tags(
    asset_type: str,
    name: str,
    base: Path | None = None,
) -> dict[str, str]:
    """Return all tags for an asset as ``{tag_name: version}``."""
    td = _tags_dir(asset_type, name, base)
    if not td.exists():
        return {}
    return {
        f.name: f.read_text(encoding="utf-8").strip()
        for f in sorted(td.iterdir())
        if f.is_file()
    }


# ---------------------------------------------------------------------------
# Reference resolution
# ---------------------------------------------------------------------------


def _asset_version_file(
    hd: Path, asset_type: str, name: str, version: str
) -> Path:
    ext = "json" if asset_type == "schema" else "yaml"
    return hd / f"{asset_type}s" / name / f"{version}.{ext}"


def _resolve_version_for_asset(
    asset_type: str,
    ref: AssetRef,
    base: Path | None = None,
) -> str | None:
    """Return the concrete version string for *ref*, or ``None`` if unresolvable."""
    hd = harness_dir(base)

    if asset_type == "rule":
        rule_file = hd / "rules" / f"{ref.name}.yaml"
        return "current" if rule_file.exists() else None

    asset_dir = hd / f"{asset_type}s" / ref.name

    if ref.ref_kind == "exact":
        vf = _asset_version_file(hd, asset_type, ref.name, ref.version)  # type: ignore[arg-type]
        return ref.version if vf.exists() else None

    if ref.ref_kind == "tag":
        tag_version = get_tag_version(asset_type, ref.name, ref.tag, base)  # type: ignore[arg-type]
        if tag_version is None:
            return None
        vf = _asset_version_file(hd, asset_type, ref.name, tag_version)
        return tag_version if vf.exists() else None

    # "current"
    current_file = asset_dir / "_current"
    if not current_file.exists():
        return None
    version = current_file.read_text(encoding="utf-8").strip()
    vf = _asset_version_file(hd, asset_type, ref.name, version)
    return version if vf.exists() else None


def resolve_ref(
    ref: str | AssetRef,
    asset_type: str,
    base: Path | None = None,
) -> str | None:
    """Resolve a reference to a concrete version string.

    Returns the resolved version string (e.g. ``"v0.1.0"``), ``"current"``
    for rules, or ``None`` if the reference cannot be resolved.
    """
    if isinstance(ref, str):
        ref = parse_ref(ref)
    return _resolve_version_for_asset(asset_type, ref, base)


def check_ref_exists(
    asset_type: str,
    ref: str | AssetRef,
    base: Path | None = None,
) -> bool:
    """Return ``True`` if the referenced asset exists in the workspace."""
    return resolve_ref(ref, asset_type, base) is not None


# ---------------------------------------------------------------------------
# Dependency graph and circular reference detection
# ---------------------------------------------------------------------------


def build_dependency_graph(
    asset_nodes: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Build a dependency graph from a list of node dicts.

    Each dict must have:
      - ``"id"`` — unique node identifier (e.g. ``"prompt:code-reviewer"``)
      - ``"refs"`` — list of node ids this asset depends on (may be absent)

    Returns ``{node_id: [dep_id, ...]}``.
    """
    return {item["id"]: list(item.get("refs", [])) for item in asset_nodes}


def detect_circular_refs(
    graph: dict[str, list[str]],
) -> list[list[str]]:
    """Detect cycles in a dependency graph using iterative DFS.

    Returns a list of cycles; each cycle is a list of node ids forming the loop.
    """
    visited: set[str] = set()
    cycles: list[list[str]] = []

    def dfs(node: str, path: list[str], in_stack: set[str]) -> None:
        if node in in_stack:
            start = path.index(node)
            cycles.append(path[start:] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        in_stack.add(node)
        path.append(node)
        for dep in graph.get(node, []):
            dfs(dep, path, in_stack)
        path.pop()
        in_stack.discard(node)

    for node in list(graph):
        if node not in visited:
            dfs(node, [], set())

    return cycles


# ---------------------------------------------------------------------------
# Doctor health models
# ---------------------------------------------------------------------------


@dataclass
class AssetHealth:
    """Health record for a single asset."""

    asset_type: str
    name: str
    version: str | None          # current version (None if indeterminate)
    broken: bool                  # True when the asset has a structural problem
    issue: str | None             # Human-readable description of the problem
    tags: dict[str, str] = field(default_factory=dict)       # tag → version
    broken_tags: list[str] = field(default_factory=list)     # tags with missing targets


@dataclass
class DoctorReport:
    """Full health report produced by :func:`run_doctor`."""

    assets: list[AssetHealth]
    cycles: list[list[str]]
    unused_assets: list[tuple[str, str]]  # (asset_type, name)

    @property
    def broken_count(self) -> int:
        return sum(1 for a in self.assets if a.broken) + sum(
            len(a.broken_tags) for a in self.assets
        )

    @property
    def is_healthy(self) -> bool:
        return self.broken_count == 0 and not self.cycles


# ---------------------------------------------------------------------------
# Doctor scan internals
# ---------------------------------------------------------------------------


def _scan_versioned_asset_type(
    asset_type: str,
    base: Path | None = None,
) -> list[AssetHealth]:
    """Scan all assets of one versioned type and return health records."""
    hd = harness_dir(base)
    assets_dir = hd / f"{asset_type}s"
    ext = "json" if asset_type == "schema" else "yaml"
    results: list[AssetHealth] = []

    if not assets_dir.exists():
        return results

    for d in sorted(assets_dir.iterdir()):
        if not d.is_dir():
            continue
        name = d.name

        current_file = d / "_current"
        broken = False
        issue: str | None = None
        current_version: str | None = None

        if not current_file.exists():
            broken = True
            issue = "missing _current pointer file"
        else:
            current_version = current_file.read_text(encoding="utf-8").strip()
            if not current_version:
                broken = True
                issue = "_current file is empty"
            elif not (d / f"{current_version}.{ext}").exists():
                broken = True
                issue = f"_current points to '{current_version}' which does not exist"

        # Validate tags
        tags = list_tags(asset_type, name, base)
        broken_tags: list[str] = []
        for tag_name, tag_version in tags.items():
            if not (d / f"{tag_version}.{ext}").exists():
                broken_tags.append(tag_name)

        results.append(
            AssetHealth(
                asset_type=asset_type,
                name=name,
                version=current_version,
                broken=broken,
                issue=issue,
                tags=tags,
                broken_tags=broken_tags,
            )
        )

    return results


def _scan_rules(base: Path | None = None) -> list[AssetHealth]:
    """Scan all rules and return health records."""
    hd = harness_dir(base)
    rules_dir = hd / "rules"
    results: list[AssetHealth] = []

    if not rules_dir.exists():
        return results

    for f in sorted(rules_dir.iterdir()):
        if not f.is_file() or f.suffix != ".yaml":
            continue
        name = f.stem
        broken = False
        issue: str | None = None

        try:
            with f.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if not isinstance(data, dict):
                broken = True
                issue = "invalid YAML: expected a mapping"
            elif not data.get("name"):
                broken = True
                issue = "missing required field 'name'"
        except Exception as exc:
            broken = True
            issue = f"YAML parse error: {exc}"

        results.append(
            AssetHealth(
                asset_type="rule",
                name=name,
                version="current",
                broken=broken,
                issue=issue,
            )
        )

    return results


def _collect_ref_strings_from_dir(scan_dir: Path) -> set[str]:
    """Collect all word-tokens from YAML/JSON files under *scan_dir*."""
    tokens: set[str] = set()
    if not scan_dir.exists():
        return tokens
    # Match bare names and name@qualifier patterns
    pattern = re.compile(r"[\w-]+(?:@(?:v\d+\.\d+\.\d+|[\w-]+))?")
    for f in scan_dir.rglob("*.yaml"):
        try:
            for m in pattern.finditer(f.read_text(encoding="utf-8")):
                tokens.add(m.group(0))
        except Exception:
            pass
    for f in scan_dir.rglob("*.json"):
        try:
            for m in pattern.finditer(f.read_text(encoding="utf-8")):
                tokens.add(m.group(0))
        except Exception:
            pass
    return tokens


def find_unused_assets(
    all_assets: list[AssetHealth],
    base: Path | None = None,
) -> list[tuple[str, str]]:
    """Return assets not referenced by any consumer definition.

    Scans skill, harness, agent, and blueprint directories for references.
    An asset is considered *unused* when neither its bare name nor any
    ``name@qualifier`` token appears in those files.

    Returns a list of ``(asset_type, name)`` tuples.
    """
    hd = harness_dir(base)
    all_refs: set[str] = set()
    for subdir in CONSUMER_SUBDIRS:
        all_refs |= _collect_ref_strings_from_dir(hd / subdir)

    unused: list[tuple[str, str]] = []
    for asset in all_assets:
        name = asset.name
        referenced = name in all_refs or any(
            token == name or token.startswith(f"{name}@") for token in all_refs
        )
        if not referenced:
            unused.append((asset.asset_type, name))
    return unused


# ---------------------------------------------------------------------------
# Public doctor entry point
# ---------------------------------------------------------------------------


def run_doctor(base: Path | None = None) -> DoctorReport:
    """Run a full health scan of the ``.harness/`` workspace.

    Checks:
    - ``_current`` pointer integrity for all versioned assets
    - Tag pointer integrity
    - Circular dependencies between assets
    - Unreferenced (unused) assets

    Returns a :class:`DoctorReport`.
    """
    all_assets: list[AssetHealth] = []
    for asset_type in ("prompt", "schema", "context"):
        all_assets.extend(_scan_versioned_asset_type(asset_type, base))
    all_assets.extend(_scan_rules(base))

    # Build dependency graph (Phase 1: no inter-asset references exist yet;
    # graph will be enriched in Phase 2+ when skills reference primitives)
    graph: dict[str, list[str]] = {
        f"{a.asset_type}:{a.name}": [] for a in all_assets
    }
    cycles = detect_circular_refs(graph)

    unused = find_unused_assets(all_assets, base)

    return DoctorReport(assets=all_assets, cycles=cycles, unused_assets=unused)
