"""Config read/write module for .harness/config.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

HARNESS_DIR = ".harness"
CONFIG_FILE = "config.yaml"

SUBDIRS = [
    "prompts",
    "schemas",
    "contexts",
    "rules",
    "skills",
    "harnesses",
    "agents",
    "blueprints",
    "logs",
    "evals",
    "improvements",
    "memory",
]

DEFAULT_CONFIG: dict[str, Any] = {
    "default_model": "gpt-4o",
    "api_key": "${OPENAI_API_KEY}",
    "log_level": "INFO",
}


def harness_dir(base: Path | None = None) -> Path:
    return (base or Path.cwd()) / HARNESS_DIR


def config_path(base: Path | None = None) -> Path:
    return harness_dir(base) / CONFIG_FILE


def is_initialized(base: Path | None = None) -> bool:
    return config_path(base).exists()


def read_config(base: Path | None = None) -> dict[str, Any]:
    path = config_path(base)
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_config(data: dict[str, Any], base: Path | None = None) -> None:
    path = config_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def init_harness(base: Path | None = None) -> None:
    """Create .harness/ directory tree and default config.yaml."""
    root = harness_dir(base)
    root.mkdir(parents=True, exist_ok=True)
    for sub in SUBDIRS:
        (root / sub).mkdir(exist_ok=True)
    write_config(DEFAULT_CONFIG, base)
