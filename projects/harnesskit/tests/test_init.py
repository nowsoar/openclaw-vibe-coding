"""Tests for Phase 1.1: project initialization."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from harness_kit.cli import app
from harness_kit.config import (
    DEFAULT_CONFIG,
    SUBDIRS,
    config_path,
    harness_dir,
    init_harness,
    is_initialized,
    read_config,
    write_config,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# config module unit tests
# ---------------------------------------------------------------------------


class TestIsInitialized:
    def test_false_when_no_harness_dir(self, tmp_path: Path) -> None:
        assert not is_initialized(tmp_path)

    def test_true_after_init(self, tmp_path: Path) -> None:
        init_harness(tmp_path)
        assert is_initialized(tmp_path)


class TestInitHarness:
    def test_creates_harness_dir(self, tmp_path: Path) -> None:
        init_harness(tmp_path)
        assert harness_dir(tmp_path).is_dir()

    def test_creates_all_subdirs(self, tmp_path: Path) -> None:
        init_harness(tmp_path)
        for sub in SUBDIRS:
            assert (harness_dir(tmp_path) / sub).is_dir(), f"Missing subdir: {sub}"

    def test_creates_config_yaml(self, tmp_path: Path) -> None:
        init_harness(tmp_path)
        assert config_path(tmp_path).exists()

    def test_config_has_defaults(self, tmp_path: Path) -> None:
        init_harness(tmp_path)
        cfg = read_config(tmp_path)
        assert cfg["default_model"] == DEFAULT_CONFIG["default_model"]
        assert cfg["log_level"] == DEFAULT_CONFIG["log_level"]
        assert cfg["api_key"] == DEFAULT_CONFIG["api_key"]

    def test_idempotent(self, tmp_path: Path) -> None:
        init_harness(tmp_path)
        init_harness(tmp_path)  # second call must not raise
        assert is_initialized(tmp_path)


class TestReadWriteConfig:
    def test_roundtrip(self, tmp_path: Path) -> None:
        data = {"default_model": "claude-3-5-sonnet", "log_level": "DEBUG", "api_key": "${ANTHROPIC_API_KEY}"}
        write_config(data, tmp_path)
        assert read_config(tmp_path) == data

    def test_yaml_format(self, tmp_path: Path) -> None:
        write_config(DEFAULT_CONFIG, tmp_path)
        raw = config_path(tmp_path).read_text(encoding="utf-8")
        parsed = yaml.safe_load(raw)
        assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestInitCommand:
    def test_init_succeeds(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init"], catch_exceptions=False)
        assert result.exit_code == 0

    def test_init_creates_structure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init"], catch_exceptions=False)
        assert result.exit_code == 0
        assert is_initialized(tmp_path)
        for sub in SUBDIRS:
            assert (harness_dir(tmp_path) / sub).is_dir()

    def test_init_output_contains_initialized(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Initialized" in result.output

    def test_init_repeat_shows_already_initialized(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"], catch_exceptions=False)
        result = runner.invoke(app, ["init"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Already initialized" in result.output

    def test_init_config_yaml_valid(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"], catch_exceptions=False)
        cfg = read_config(tmp_path)
        assert "default_model" in cfg
        assert "log_level" in cfg
        assert "api_key" in cfg
