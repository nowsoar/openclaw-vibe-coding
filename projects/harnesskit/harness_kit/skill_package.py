"""Skill packaging — publish (export .hsk) and install from file or Git URL."""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from harness_kit.config import harness_dir, init_harness, is_initialized
from harness_kit.registry import register_skill


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_ref(ref: str) -> tuple[str, str | None]:
    """'name@version' -> (name, version).  'name' -> (name, None)."""
    if "@" in ref:
        name, version = ref.split("@", 1)
        return name.strip(), version.strip()
    return ref.strip(), None


def _get_current_version(asset_dir: Path, name: str) -> str | None:
    cf = asset_dir / name / "_current"
    if cf.exists():
        return cf.read_text(encoding="utf-8").strip()
    return None


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------


def publish_skill(
    name: str,
    version: str | None = None,
    output_dir: Path | None = None,
    base: Path | None = None,
) -> Path:
    """Package a skill and its dependencies into a .hsk file (zip).

    Returns the path to the created package.
    """
    from harness_kit.skill import load_skill, get_skill_deps, skills_dir  # noqa: PLC0415

    hd = harness_dir(base)
    skill_data = load_skill(name, version, base)
    skill_version = skill_data["version"]

    out_dir = output_dir or Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)
    pkg_path = out_dir / f"{name}-{skill_version}.hsk"

    # Collect files to bundle
    files_to_add: list[tuple[Path, str]] = []  # (real_path, arc_path)

    # Skill YAML itself
    skill_file = skills_dir(base) / name / f"{skill_version}.yaml"
    if skill_file.exists():
        files_to_add.append((skill_file, f"skills/{name}/{skill_version}.yaml"))

    # Dependencies
    deps = get_skill_deps(name, skill_version, base)

    for prompt_ref in deps["prompts"]:
        pname, pver = _parse_ref(prompt_ref)
        prompts_dir = hd / "prompts" / pname
        if pver is None:
            pver = _get_current_version(hd / "prompts", pname)
        if pver:
            pfile = prompts_dir / f"{pver}.yaml"
            if pfile.exists():
                files_to_add.append((pfile, f"prompts/{pname}/{pver}.yaml"))

    for schema_ref in deps["schemas"]:
        sname, sver = _parse_ref(schema_ref)
        schemas_dir = hd / "schemas" / sname
        if sver is None:
            sver = _get_current_version(hd / "schemas", sname)
        if sver:
            sfile = schemas_dir / f"{sver}.json"
            if sfile.exists():
                files_to_add.append((sfile, f"schemas/{sname}/{sver}.json"))

    for rule_ref in deps["rules"]:
        rname, _ = _parse_ref(rule_ref)
        rfile = hd / "rules" / f"{rname}.yaml"
        if rfile.exists():
            files_to_add.append((rfile, f"rules/{rname}.yaml"))

    for ctx_ref in deps["context"]:
        cname, cver = _parse_ref(ctx_ref)
        if cver is None:
            cver = _get_current_version(hd / "contexts", cname)
        if cver:
            cfile = hd / "contexts" / cname / f"{cver}.yaml"
            if cfile.exists():
                files_to_add.append((cfile, f"contexts/{cname}/{cver}.yaml"))

    # Build manifest
    manifest: dict[str, Any] = {
        "skill_name": name,
        "skill_version": skill_version,
        "packaged_at": datetime.now(tz=timezone.utc).isoformat(),
        "description": skill_data.get("description", ""),
        "files": [arc for _, arc in files_to_add],
    }

    with zipfile.ZipFile(pkg_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        for real_path, arc_path in files_to_add:
            zf.write(real_path, arc_path)

    return pkg_path


# ---------------------------------------------------------------------------
# Install from local file (.hsk or .yaml)
# ---------------------------------------------------------------------------


def install_skill_from_path(source_path: Path, base: Path | None = None) -> str:
    """Install a skill from a local .hsk package or .yaml file.

    Returns the installed skill name.
    """
    if not source_path.exists():
        raise FileNotFoundError(f"Source not found: {source_path}")

    hd = harness_dir(base)

    if source_path.suffix == ".hsk":
        return _install_from_hsk(source_path, hd, base)
    elif source_path.suffix in (".yaml", ".yml"):
        return _install_from_yaml(source_path, base)
    else:
        raise ValueError(f"Unsupported file format: {source_path.suffix}. Expected .hsk or .yaml")


def _install_from_yaml(source_path: Path, base: Path | None) -> str:
    """Install a skill from a standalone YAML file."""
    from harness_kit.skill import save_skill_from_dict  # noqa: PLC0415

    data = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Invalid skill YAML: expected a mapping at top level.")

    name = data.get("name")
    if not name:
        raise ValueError("Skill YAML must have a 'name' field.")

    save_skill_from_dict(data, base)
    register_skill(
        name=name,
        version=data.get("version", "v0.0.1"),
        source=str(source_path.resolve()),
        description=data.get("description", ""),
        tags=data.get("tags", []),
    )
    return name


def _install_from_hsk(pkg_path: Path, hd: Path, base: Path | None) -> str:
    """Install a skill from a .hsk (zip) package, restoring all bundled assets."""
    with zipfile.ZipFile(pkg_path, "r") as zf:
        # Read manifest
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        skill_name: str = manifest["skill_name"]
        skill_version: str = manifest["skill_version"]

        for arc_path in zf.namelist():
            if arc_path == "manifest.json":
                continue
            dest = hd / arc_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(arc_path))

        # Write _current markers for skill and versioned dependencies
        skill_current = hd / "skills" / skill_name / "_current"
        skill_current.write_text(skill_version, encoding="utf-8")

        # Write _current for each versioned dep bundled
        _ensure_current_markers_from_manifest(hd, manifest.get("files", []))

    register_skill(
        name=skill_name,
        version=skill_version,
        source=str(pkg_path.resolve()),
        description=manifest.get("description", ""),
    )
    return skill_name


def _ensure_current_markers_from_manifest(hd: Path, files: list[str]) -> None:
    """Write _current marker files for any versioned assets extracted from .hsk."""
    for arc_path in files:
        parts = Path(arc_path).parts  # e.g. ('prompts', 'name', 'v0.1.0.yaml')
        if len(parts) == 3 and parts[0] in ("prompts", "schemas", "contexts", "skills"):
            asset_type = parts[0]
            asset_name = parts[1]
            filename = parts[2]  # e.g. 'v0.1.0.yaml' or 'v0.1.0.json'
            version = Path(filename).stem  # strip extension
            if version.startswith("v"):
                current_file = hd / asset_type / asset_name / "_current"
                # Only write if not already set (don't override existing current)
                if not current_file.exists():
                    current_file.write_text(version, encoding="utf-8")


# ---------------------------------------------------------------------------
# Install from Git URL
# ---------------------------------------------------------------------------


def install_skill_from_git(git_url: str, base: Path | None = None) -> str:
    """Install a skill from a Git URL.

    Supported formats:
      - github:user/repo/path/to/skill.yaml
      - https://raw.githubusercontent.com/user/repo/branch/path/skill.yaml
      - https://github.com/user/repo/raw/branch/path/skill.yaml
    """
    raw_url = _resolve_raw_url(git_url)
    yaml_content = _fetch_url(raw_url)

    data = yaml.safe_load(yaml_content)
    if not isinstance(data, dict):
        raise ValueError("Invalid skill YAML fetched from URL.")

    from harness_kit.skill import save_skill_from_dict  # noqa: PLC0415

    name = data.get("name")
    if not name:
        raise ValueError("Fetched skill YAML has no 'name' field.")

    save_skill_from_dict(data, base)
    register_skill(
        name=name,
        version=data.get("version", "v0.0.1"),
        source=git_url,
        description=data.get("description", ""),
        tags=data.get("tags", []),
    )
    return name


def _resolve_raw_url(git_url: str) -> str:
    """Convert various Git URL formats to a raw content URL."""
    if git_url.startswith("github:"):
        # github:user/repo/branch/path/to/file.yaml
        rest = git_url[len("github:"):]
        parts = rest.split("/")
        if len(parts) < 3:
            raise ValueError(
                "github: URL must be: github:user/repo/branch/path/to/skill.yaml"
            )
        user = parts[0]
        repo = parts[1]
        path = "/".join(parts[2:])
        return f"https://raw.githubusercontent.com/{user}/{repo}/{path}"
    # Already a raw URL or https:// URL
    return git_url


def _fetch_url(url: str) -> str:
    """Download text content from a URL."""
    import urllib.request  # noqa: PLC0415

    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
        return resp.read().decode("utf-8")
