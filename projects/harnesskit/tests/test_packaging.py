"""Phase 8.9 — package metadata & distribution readiness tests."""
import importlib
import importlib.metadata
import subprocess
import sys
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


# ---------------------------------------------------------------------------
# Import / entry-point tests
# ---------------------------------------------------------------------------


def test_package_importable():
    """harness_kit package can be imported."""
    import harness_kit  # noqa: F401


def test_cli_module_importable():
    """CLI module and typer app are importable."""
    from harness_kit.cli import app  # noqa: F401


def test_entry_point_registered():
    """harnesskit console_scripts entry point is registered."""
    eps = importlib.metadata.entry_points(group="console_scripts")
    names = [ep.name for ep in eps]
    assert "harnesskit" in names, f"entry points found: {names}"


def test_cli_help_exits_zero():
    """harnesskit --help exits with code 0."""
    result = subprocess.run(
        [sys.executable, "-m", "harness_kit.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# Package metadata tests (requires installed editable package)
# ---------------------------------------------------------------------------


def test_version_metadata():
    """Package exposes correct name and version via importlib.metadata."""
    meta = importlib.metadata.metadata("harness-kit")
    assert meta["Name"].lower() == "harness-kit"
    assert meta["Version"] == "0.1.0"


def test_metadata_summary():
    """Package Summary field is non-empty."""
    meta = importlib.metadata.metadata("harness-kit")
    assert meta["Summary"], "Summary should not be empty"


def test_metadata_requires_python():
    """Package declares a minimum Python version."""
    meta = importlib.metadata.metadata("harness-kit")
    assert meta["Requires-Python"], "Requires-Python should be set"
    assert "3.10" in meta["Requires-Python"]


# ---------------------------------------------------------------------------
# pyproject.toml content tests (packaging readiness)
# ---------------------------------------------------------------------------


def test_pyproject_license():
    """pyproject.toml declares a license."""
    content = PYPROJECT.read_text()
    assert "license" in content


def test_pyproject_authors():
    """pyproject.toml declares at least one author."""
    content = PYPROJECT.read_text()
    assert "authors" in content


def test_pyproject_keywords():
    """pyproject.toml contains keywords for PyPI discoverability."""
    content = PYPROJECT.read_text()
    assert "keywords" in content
    assert "ai" in content or "llm" in content or "agent" in content


def test_pyproject_classifiers():
    """pyproject.toml contains PyPI classifiers."""
    content = PYPROJECT.read_text()
    assert "classifiers" in content
    assert "Programming Language :: Python :: 3" in content


def test_pyproject_classifier_license():
    """Classifiers include an OSI-approved license entry."""
    content = PYPROJECT.read_text()
    assert "License :: OSI Approved" in content


def test_pyproject_project_urls():
    """pyproject.toml declares [project.urls] for PyPI sidebar links."""
    content = PYPROJECT.read_text()
    assert "[project.urls]" in content
    assert "Homepage" in content or "Repository" in content


def test_pyproject_dev_extras():
    """[project.optional-dependencies] includes a 'dev' group with pytest."""
    content = PYPROJECT.read_text()
    assert "pytest" in content


def test_pyproject_entry_point():
    """pyproject.toml declares the harnesskit console script."""
    content = PYPROJECT.read_text()
    assert "harnesskit" in content
    assert "harness_kit.cli:app" in content


# ---------------------------------------------------------------------------
# Build-readiness check (skip when `build` package is absent)
# ---------------------------------------------------------------------------

_HAS_BUILD = (
    subprocess.run(
        [sys.executable, "-m", "build", "--version"],
        capture_output=True,
    ).returncode
    == 0
)


@pytest.mark.skipif(not _HAS_BUILD, reason="'build' package not installed")
def test_wheel_builds(tmp_path):
    """Package can be built into a wheel with `python -m build --wheel`."""
    project_root = Path(__file__).parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )
    assert result.returncode == 0, f"build failed:\n{result.stderr}"
    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1, f"Expected 1 wheel file, found: {wheels}"
    assert "harness" in wheels[0].name.lower()


@pytest.mark.skipif(not _HAS_BUILD, reason="'build' package not installed")
def test_sdist_builds(tmp_path):
    """Package can be built into a source distribution with `python -m build --sdist`."""
    project_root = Path(__file__).parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "build", "--sdist", "--outdir", str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )
    assert result.returncode == 0, f"build failed:\n{result.stderr}"
    sdists = list(tmp_path.glob("*.tar.gz"))
    assert len(sdists) == 1, f"Expected 1 sdist, found: {sdists}"
