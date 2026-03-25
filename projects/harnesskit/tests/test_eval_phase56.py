"""Tests for Phase 5.6: eval system integration (CI mode, JUnit XML, trend, harness eval-suite binding)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from harness_kit import eval as em
from harness_kit import harness as hm
from harness_kit.cli import app
from harness_kit.config import init_harness

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


SIMPLE_SUITE: dict[str, Any] = {
    "name": "simple-suite",
    "description": "Simple test suite",
    "cases": [
        {
            "id": "case-a",
            "name": "Case A",
            "inputs": {"x": "1"},
            "assertions": [
                {"type": "contains", "path": "$.result", "value": "ok"},
            ],
        },
        {
            "id": "case-b",
            "name": "Case B",
            "inputs": {"x": "2"},
            "assertions": [
                {"type": "contains", "path": "$.result", "value": "ok"},
            ],
        },
    ],
}


def _make_invoke_always_pass(output: str = '{"result": "ok"}'):
    """Return an invoke_fn that always returns a passing output."""
    def _invoke(inputs: dict) -> tuple[str, int, int, float]:
        return output, 10, 20, 0.5
    return _invoke


def _make_invoke_always_fail():
    """Return an invoke_fn that always returns failing output."""
    def _invoke(inputs: dict) -> tuple[str, int, int, float]:
        return '{"result": "bad"}', 10, 20, 0.5
    return _invoke


# ---------------------------------------------------------------------------
# JUnit XML generation
# ---------------------------------------------------------------------------


class TestGenerateJunitXml:
    def test_all_passed(self, workspace: Path) -> None:
        em.save_suite(SIMPLE_SUITE, workspace)
        report = em.run_eval(
            target="my-skill@v0.1.0",
            suite_name="simple-suite",
            invoke_fn=_make_invoke_always_pass(),
            base=workspace,
        )
        xml_path = workspace / "results.xml"
        em.generate_junit_xml(report, xml_path)
        assert xml_path.exists()

        tree = ET.parse(xml_path)
        root = tree.getroot()
        assert root.tag == "testsuites"
        assert root.attrib["tests"] == "2"
        assert root.attrib["failures"] == "0"
        assert root.attrib["errors"] == "0"

        testcases = root.findall(".//testcase")
        assert len(testcases) == 2
        for tc in testcases:
            assert tc.find("failure") is None
            assert tc.find("error") is None

    def test_some_failures(self, workspace: Path) -> None:
        em.save_suite(SIMPLE_SUITE, workspace)
        report = em.run_eval(
            target="my-skill@v0.1.0",
            suite_name="simple-suite",
            invoke_fn=_make_invoke_always_fail(),
            base=workspace,
        )
        xml_path = workspace / "results.xml"
        em.generate_junit_xml(report, xml_path)
        assert xml_path.exists()

        tree = ET.parse(xml_path)
        root = tree.getroot()
        assert root.attrib["tests"] == "2"
        # Both cases fail
        failures_in_tc = root.findall(".//testcase/failure")
        assert len(failures_in_tc) == 2

    def test_xml_has_valid_declaration(self, workspace: Path) -> None:
        em.save_suite(SIMPLE_SUITE, workspace)
        report = em.run_eval(
            target="skill@v1",
            suite_name="simple-suite",
            invoke_fn=_make_invoke_always_pass(),
            base=workspace,
        )
        xml_path = workspace / "out.xml"
        em.generate_junit_xml(report, xml_path)
        content = xml_path.read_bytes()
        assert content.startswith(b"<?xml")

    def test_error_case_produces_error_element(self, workspace: Path) -> None:
        suite = {
            "name": "err-suite",
            "description": "error suite",
            "cases": [
                {
                    "id": "error-case",
                    "name": "Raises",
                    "inputs": {},
                    "assertions": [{"type": "contains", "path": "$.x", "value": "y"}],
                }
            ],
        }
        em.save_suite(suite, workspace)

        def _crash(inputs):
            raise RuntimeError("boom")

        report = em.run_eval("skill@v0", "err-suite", _crash, base=workspace)
        xml_path = workspace / "err.xml"
        em.generate_junit_xml(report, xml_path)
        tree = ET.parse(xml_path)
        root = tree.getroot()
        error_els = root.findall(".//testcase/error")
        assert len(error_els) == 1

    def test_creates_parent_dirs(self, workspace: Path) -> None:
        em.save_suite(SIMPLE_SUITE, workspace)
        report = em.run_eval("s@v1", "simple-suite", _make_invoke_always_pass(), base=workspace)
        xml_path = workspace / "nested" / "dir" / "results.xml"
        em.generate_junit_xml(report, xml_path)
        assert xml_path.exists()


# ---------------------------------------------------------------------------
# CI mode: exit code
# ---------------------------------------------------------------------------


class TestCiMode:
    def test_ci_exits_nonzero_on_failure(self, workspace: Path) -> None:
        """CI mode should return exit code 1 when tests fail (mocked LLM)."""
        em.save_suite(SIMPLE_SUITE, workspace)

        # Write a fake skill
        skills_dir = workspace / ".harness" / "skills" / "my-skill"
        skills_dir.mkdir(parents=True)
        skill_data = {
            "name": "my-skill",
            "version": "v0.1.0",
            "description": "test",
            "inputs": [],
            "outputs": [],
            "assets": {},
        }
        (skills_dir / "v0.1.0.yaml").write_text(yaml.dump(skill_data))
        (skills_dir / "_current").write_text("v0.1.0")

        with (
            patch("harness_kit.cli.call_llm") as mock_llm,
            patch("harness_kit.cli._skill_mod.render_skill_prompt", return_value={}),
        ):
            resp = MagicMock()
            resp.content = '{"result": "bad"}'
            resp.input_tokens = 10
            resp.output_tokens = 20
            resp.duration = 0.5
            mock_llm.return_value = resp

            result = runner.invoke(
                app,
                ["eval", "run", "my-skill", "--suite", "simple-suite", "--ci"],
                env={"OPENAI_API_KEY": "test-key"},
            )
        assert result.exit_code == 1

    def test_ci_exits_zero_on_pass(self, workspace: Path) -> None:
        em.save_suite(SIMPLE_SUITE, workspace)

        skills_dir = workspace / ".harness" / "skills" / "my-skill"
        skills_dir.mkdir(parents=True)
        skill_data = {
            "name": "my-skill",
            "version": "v0.1.0",
            "description": "test",
            "inputs": [],
            "outputs": [],
            "assets": {},
        }
        (skills_dir / "v0.1.0.yaml").write_text(yaml.dump(skill_data))
        (skills_dir / "_current").write_text("v0.1.0")

        with (
            patch("harness_kit.cli.call_llm") as mock_llm,
            patch("harness_kit.cli._skill_mod.render_skill_prompt", return_value={}),
        ):
            resp = MagicMock()
            resp.content = '{"result": "ok"}'
            resp.input_tokens = 10
            resp.output_tokens = 20
            resp.duration = 0.5
            mock_llm.return_value = resp

            result = runner.invoke(
                app,
                ["eval", "run", "my-skill", "--suite", "simple-suite", "--ci"],
                env={"OPENAI_API_KEY": "test-key"},
            )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Harness eval-suite binding
# ---------------------------------------------------------------------------


class TestHarnessEvalSuite:
    def test_create_harness_with_eval_suite(self, workspace: Path) -> None:
        em.save_suite(SIMPLE_SUITE, workspace)
        version, is_new = hm.save_harness(
            name="my-harness",
            description="test harness",
            eval_suite="simple-suite",
            base=workspace,
        )
        assert is_new
        data = hm.load_harness("my-harness", base=workspace)
        assert data.get("eval_suite") == "simple-suite"

    def test_save_harness_from_dict_preserves_eval_suite(self, workspace: Path) -> None:
        data = {
            "name": "h2",
            "description": "desc",
            "skills": [],
            "eval_suite": "simple-suite",
        }
        hm.save_harness_from_dict(data, base=workspace)
        loaded = hm.load_harness("h2", base=workspace)
        assert loaded.get("eval_suite") == "simple-suite"

    def test_harness_without_eval_suite_has_no_field(self, workspace: Path) -> None:
        hm.save_harness(name="plain-harness", description="no eval", base=workspace)
        data = hm.load_harness("plain-harness", base=workspace)
        assert "eval_suite" not in data

    def test_cli_harness_create_with_eval_suite(self, workspace: Path) -> None:
        em.save_suite(SIMPLE_SUITE, workspace)
        result = runner.invoke(
            app,
            [
                "harness", "create", "bound-harness",
                "--description", "bound",
                "--eval-suite", "simple-suite",
            ],
        )
        assert result.exit_code == 0
        assert "simple-suite" in result.output

        data = hm.load_harness("bound-harness", base=workspace)
        assert data.get("eval_suite") == "simple-suite"


# ---------------------------------------------------------------------------
# Eval trend
# ---------------------------------------------------------------------------


class TestEvalTrend:
    def _seed_results(self, workspace: Path, n: int = 5) -> None:
        """Save n fake eval results with varying pass rates."""
        em.save_suite(SIMPLE_SUITE, workspace)
        for i in range(n):
            total = 2
            passed = i % 3  # 0, 1, 2, 0, 1 → varying rates
            passed = min(passed, total)
            # Build a fake report directly
            report = {
                "timestamp": f"2026-01-{i + 1:02d}T12:00:00+00:00",
                "target": f"my-skill@v0.{i}.0",
                "suite": "simple-suite",
                "summary": {"total": total, "passed": passed, "failed": total - passed},
                "cases": [],
            }
            rdir = em.results_dir(workspace)
            rdir.mkdir(parents=True, exist_ok=True)
            (rdir / f"2026-01-{i + 1:02d}T12-00-00-000.json").write_text(
                json.dumps(report)
            )

    def test_trend_returns_entries(self, workspace: Path) -> None:
        self._seed_results(workspace, n=3)
        entries = em.eval_trend(base=workspace)
        assert len(entries) == 3
        for entry in entries:
            assert "pass_rate" in entry
            assert "timestamp" in entry
            assert "target" in entry
            assert "suite" in entry

    def test_trend_filter_by_target(self, workspace: Path) -> None:
        self._seed_results(workspace, n=4)
        # Add an unrelated entry
        rdir = em.results_dir(workspace)
        other = {
            "timestamp": "2026-01-10T12:00:00+00:00",
            "target": "other-skill@v1.0.0",
            "suite": "other-suite",
            "summary": {"total": 1, "passed": 1, "failed": 0},
            "cases": [],
        }
        (rdir / "2026-01-10T12-00-00-000.json").write_text(json.dumps(other))

        entries = em.eval_trend(target_filter="my-skill", base=workspace)
        assert all("my-skill" in e["target"] for e in entries)

    def test_trend_filter_by_suite(self, workspace: Path) -> None:
        self._seed_results(workspace, n=3)
        entries_all = em.eval_trend(base=workspace)
        entries_filtered = em.eval_trend(suite_filter="simple-suite", base=workspace)
        assert len(entries_filtered) <= len(entries_all)
        assert all(e["suite"] == "simple-suite" for e in entries_filtered)

    def test_trend_respects_limit(self, workspace: Path) -> None:
        self._seed_results(workspace, n=10)
        entries = em.eval_trend(base=workspace, limit=4)
        assert len(entries) == 4

    def test_trend_empty_when_no_results(self, workspace: Path) -> None:
        entries = em.eval_trend(base=workspace)
        assert entries == []

    def test_trend_pass_rate_calculation(self, workspace: Path) -> None:
        rdir = em.results_dir(workspace)
        rdir.mkdir(parents=True, exist_ok=True)
        report = {
            "timestamp": "2026-01-01T12:00:00+00:00",
            "target": "sk@v1",
            "suite": "s",
            "summary": {"total": 4, "passed": 3, "failed": 1},
            "cases": [],
        }
        (rdir / "2026-01-01.json").write_text(json.dumps(report))
        entries = em.eval_trend(base=workspace)
        assert entries[0]["pass_rate"] == pytest.approx(0.75)
        assert entries[0]["passed"] == 3
        assert entries[0]["total"] == 4

    def test_cli_eval_trend_command(self, workspace: Path) -> None:
        self._seed_results(workspace, n=3)
        result = runner.invoke(app, ["eval", "trend"])
        assert result.exit_code == 0
        # rich may truncate column values; check partial suite name prefix
        assert "simple-s" in result.output

    def test_cli_eval_trend_no_results(self, workspace: Path) -> None:
        result = runner.invoke(app, ["eval", "trend"])
        assert result.exit_code == 0
        assert "No eval results" in result.output

    def test_cli_eval_trend_with_filter(self, workspace: Path) -> None:
        self._seed_results(workspace, n=3)
        result = runner.invoke(app, ["eval", "trend", "my-skill"])
        assert result.exit_code == 0

    def test_cli_eval_trend_limit_option(self, workspace: Path) -> None:
        self._seed_results(workspace, n=5)
        result = runner.invoke(app, ["eval", "trend", "--limit", "2"])
        assert result.exit_code == 0
