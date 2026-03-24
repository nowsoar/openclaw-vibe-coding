"""Tests for Phase 4.6: Blueprint run — real-time progress callbacks and execution reports."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit import blueprint as bm
from harness_kit.blueprint_executor import (
    BlueprintRunResult,
    StepResult,
    execute_blueprint,
    save_run_report,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Initialize a .harness workspace in a temp dir and cd into it."""
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


def _simple_blueprint(steps: list[dict], **kwargs) -> dict:
    return {
        "name": "test-pipeline",
        "version": "v0.1.0",
        "description": "Test pipeline",
        "inputs": [],
        "steps": steps,
        "outputs": {},
        **kwargs,
    }


# ---------------------------------------------------------------------------
# save_run_report() tests
# ---------------------------------------------------------------------------


class TestSaveRunReport:
    """Phase 4.6 — execution report persistence."""

    def test_report_file_created(self, tmp_base: Path) -> None:
        """save_run_report creates a JSON file in .harness/logs/blueprints/."""
        result = BlueprintRunResult(
            blueprint_name="my-pipeline",
            blueprint_version="v0.1.0",
            status="success",
            steps=[
                StepResult(
                    step_id="step1",
                    step_name="Step One",
                    step_type="deterministic",
                    status="success",
                    output="hello",
                    duration=0.5,
                    exit_code=0,
                )
            ],
            outputs={"result": "hello"},
            duration=0.5,
        )
        report_path = save_run_report(result, base=tmp_base)

        assert report_path.exists(), f"Report file not found: {report_path}"
        assert report_path.suffix == ".json"
        assert "my-pipeline" in report_path.name

    def test_report_directory_created(self, tmp_base: Path) -> None:
        """save_run_report creates .harness/logs/blueprints/ if it doesn't exist."""
        result = BlueprintRunResult(
            blueprint_name="p",
            blueprint_version="v0.1.0",
            status="success",
            steps=[],
            outputs={},
            duration=0.1,
        )
        save_run_report(result, base=tmp_base)
        assert (tmp_base / ".harness" / "logs" / "blueprints").is_dir()

    def test_report_content_structure(self, tmp_base: Path) -> None:
        """The report JSON contains required fields."""
        result = BlueprintRunResult(
            blueprint_name="pipe",
            blueprint_version="v0.2.0",
            status="stopped",
            steps=[
                StepResult(
                    step_id="lint",
                    step_name="Lint",
                    step_type="deterministic",
                    status="failed",
                    output="",
                    stderr="error",
                    exit_code=1,
                    duration=0.1,
                ),
                StepResult(
                    step_id="review",
                    step_name="Review",
                    step_type="agentic",
                    status="skipped",
                    output="",
                    duration=0.0,
                ),
            ],
            outputs={},
            duration=0.2,
            stop_reason="Step 'lint' failed",
        )
        path = save_run_report(result, base=tmp_base)
        data = json.loads(path.read_text())

        assert data["blueprint"] == "pipe"
        assert data["version"] == "v0.2.0"
        assert data["status"] == "stopped"
        assert data["stop_reason"] == "Step 'lint' failed"
        assert "timestamp" in data
        assert "duration" in data
        assert data["summary"]["total"] == 2
        assert data["summary"]["failed"] == 1
        assert data["summary"]["skipped"] == 1
        assert len(data["steps"]) == 2
        assert data["steps"][0]["id"] == "lint"
        assert data["steps"][0]["status"] == "failed"
        assert data["steps"][1]["id"] == "review"

    def test_report_summary_counts(self, tmp_base: Path) -> None:
        """summary counts success/failed/skipped/dry_run correctly."""
        steps = [
            StepResult("s1", "S1", "deterministic", "success", duration=0.1, exit_code=0),
            StepResult("s2", "S2", "deterministic", "success", duration=0.1, exit_code=0),
            StepResult("s3", "S3", "deterministic", "failed", duration=0.1, exit_code=1),
            StepResult("s4", "S4", "deterministic", "skipped", duration=0.0),
            StepResult("s5", "S5", "agentic", "dry_run", duration=0.0),
        ]
        result = BlueprintRunResult(
            blueprint_name="x",
            blueprint_version="v0.1.0",
            status="failed",
            steps=steps,
            outputs={},
            duration=0.3,
        )
        path = save_run_report(result, base=tmp_base)
        data = json.loads(path.read_text())

        assert data["summary"]["success"] == 2
        assert data["summary"]["failed"] == 1
        assert data["summary"]["skipped"] == 1
        assert data["summary"]["dry_run"] == 1
        assert data["summary"]["total"] == 5

    def test_report_output_preview_truncated(self, tmp_base: Path) -> None:
        """Long step output is truncated in the report preview."""
        long_output = "x" * 400
        result = BlueprintRunResult(
            blueprint_name="trunc",
            blueprint_version="v0.1.0",
            status="success",
            steps=[
                StepResult("s1", "S1", "deterministic", "success", output=long_output, duration=0.1, exit_code=0)
            ],
            outputs={},
            duration=0.1,
        )
        path = save_run_report(result, base=tmp_base)
        data = json.loads(path.read_text())
        preview = data["steps"][0]["output_preview"]
        assert len(preview) <= 303 + 3  # 300 chars + "..."
        assert preview.endswith("...")

    def test_multiple_reports_do_not_overwrite(self, tmp_base: Path) -> None:
        """Each save_run_report call creates a separate file (microsecond timestamp)."""
        result = BlueprintRunResult(
            blueprint_name="multi",
            blueprint_version="v0.1.0",
            status="success",
            steps=[],
            outputs={},
            duration=0.1,
        )
        p1 = save_run_report(result, base=tmp_base)
        p2 = save_run_report(result, base=tmp_base)
        assert p1 != p2


# ---------------------------------------------------------------------------
# execute_blueprint() callback tests
# ---------------------------------------------------------------------------


class TestExecuteBlueprintCallbacks:
    """Phase 4.6 — on_step_start and on_step_done callbacks."""

    def test_on_step_start_called_for_each_step(self, tmp_base: Path) -> None:
        """on_step_start is invoked once per executed step."""
        bp = _simple_blueprint([
            {"id": "s1", "type": "deterministic", "name": "S1", "run": "echo a"},
            {"id": "s2", "type": "deterministic", "name": "S2", "run": "echo b"},
        ])
        started = []
        execute_blueprint(bp, {}, base=tmp_base, on_step_start=lambda s: started.append(s["id"]))
        assert started == ["s1", "s2"]

    def test_on_step_done_called_for_each_step(self, tmp_base: Path) -> None:
        """on_step_done is invoked once per step with its StepResult."""
        bp = _simple_blueprint([
            {"id": "a", "type": "deterministic", "name": "A", "run": "echo 1"},
            {"id": "b", "type": "deterministic", "name": "B", "run": "echo 2"},
        ])
        done_ids = []
        execute_blueprint(bp, {}, base=tmp_base, on_step_done=lambda r: done_ids.append(r.step_id))
        assert done_ids == ["a", "b"]

    def test_on_step_done_receives_correct_result(self, tmp_base: Path) -> None:
        """on_step_done StepResult has correct status and output."""
        bp = _simple_blueprint([
            {"id": "greet", "type": "deterministic", "name": "Greet", "run": "echo hello"},
        ])
        results = []
        execute_blueprint(bp, {}, base=tmp_base, on_step_done=lambda r: results.append(r))
        assert results[0].status == "success"
        assert "hello" in results[0].output

    def test_callbacks_called_in_order(self, tmp_base: Path) -> None:
        """start(s1) → done(s1) → start(s2) → done(s2)."""
        bp = _simple_blueprint([
            {"id": "x", "type": "deterministic", "name": "X", "run": "echo x"},
            {"id": "y", "type": "deterministic", "name": "Y", "run": "echo y"},
        ])
        events = []
        execute_blueprint(
            bp,
            {},
            base=tmp_base,
            on_step_start=lambda s: events.append(f"start:{s['id']}"),
            on_step_done=lambda r: events.append(f"done:{r.step_id}"),
        )
        assert events == ["start:x", "done:x", "start:y", "done:y"]

    def test_callback_exception_does_not_break_execution(self, tmp_base: Path) -> None:
        """Exceptions in callbacks are silently swallowed."""
        bp = _simple_blueprint([
            {"id": "ok", "type": "deterministic", "name": "OK", "run": "echo ok"},
        ])

        def bad_callback(s):
            raise RuntimeError("callback blew up")

        result = execute_blueprint(bp, {}, base=tmp_base, on_step_start=bad_callback)
        assert result.status == "success"

    def test_callbacks_not_called_for_pre_start_skipped_steps(self, tmp_base: Path) -> None:
        """Steps skipped via start_step= don't fire start/done callbacks."""
        bp = _simple_blueprint([
            {"id": "s1", "type": "deterministic", "name": "S1", "run": "echo 1"},
            {"id": "s2", "type": "deterministic", "name": "S2", "run": "echo 2"},
        ])
        started = []
        execute_blueprint(
            bp, {}, base=tmp_base,
            start_step="s2",
            on_step_start=lambda s: started.append(s["id"]),
        )
        # Only s2 should have been started (s1 was pre-skipped)
        assert started == ["s2"]

    def test_dry_run_callbacks_invoked(self, tmp_base: Path) -> None:
        """Callbacks are also invoked in dry_run mode."""
        bp = _simple_blueprint([
            {"id": "cmd", "type": "deterministic", "name": "Cmd", "run": "echo hi"},
        ])
        done_statuses = []
        execute_blueprint(
            bp, {}, base=tmp_base,
            dry_run=True,
            on_step_done=lambda r: done_statuses.append(r.status),
        )
        assert done_statuses == ["dry_run"]


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestBlueprintRunCLIReportPhase46:
    """Phase 4.6 CLI — report file generated, progress output present."""

    def _save_bp(self, tmp_base: Path, steps: list[dict], name: str = "pipe") -> None:
        bp = {
            "name": name,
            "description": "Test",
            "inputs": [],
            "steps": steps,
            "outputs": {},
        }
        bm.save_blueprint_from_dict(bp, base=tmp_base)

    def test_run_creates_report_file(self, tmp_base: Path) -> None:
        """harnesskit blueprint run creates a report file."""
        self._save_bp(tmp_base, [
            {"id": "s1", "type": "deterministic", "name": "S1", "run": "echo hi"},
        ])
        result = runner.invoke(app, ["blueprint", "run", "pipe"])
        assert result.exit_code == 0
        report_dir = tmp_base / ".harness" / "logs" / "blueprints"
        assert report_dir.is_dir()
        reports = list(report_dir.glob("pipe-*.json"))
        assert len(reports) == 1

    def test_run_report_content_correct(self, tmp_base: Path) -> None:
        """Report JSON file has correct blueprint name and status."""
        self._save_bp(tmp_base, [
            {"id": "s1", "type": "deterministic", "name": "S1", "run": "echo hello"},
        ])
        runner.invoke(app, ["blueprint", "run", "pipe"])
        report_dir = tmp_base / ".harness" / "logs" / "blueprints"
        report_path = next(report_dir.glob("pipe-*.json"))
        data = json.loads(report_path.read_text())
        assert data["blueprint"] == "pipe"
        assert data["status"] == "success"
        assert data["summary"]["success"] == 1

    def test_run_output_shows_report_path(self, tmp_base: Path) -> None:
        """CLI output mentions the report path."""
        self._save_bp(tmp_base, [
            {"id": "s1", "type": "deterministic", "name": "S1", "run": "echo x"},
        ])
        result = runner.invoke(app, ["blueprint", "run", "pipe"])
        assert result.exit_code == 0
        assert "Report saved" in result.output

    def test_failed_run_report_status_failed_or_stopped(self, tmp_base: Path) -> None:
        """A failing blueprint still saves its report with status=stopped."""
        self._save_bp(tmp_base, [
            {"id": "bad", "type": "deterministic", "name": "Bad", "run": "exit 1", "on_fail": "stop"},
        ])
        result = runner.invoke(app, ["blueprint", "run", "pipe"])
        assert result.exit_code != 0
        report_dir = tmp_base / ".harness" / "logs" / "blueprints"
        reports = list(report_dir.glob("pipe-*.json"))
        assert len(reports) == 1
        data = json.loads(reports[0].read_text())
        assert data["status"] in ("stopped", "failed")

    def test_dry_run_report_status_dry_run(self, tmp_base: Path) -> None:
        """Dry-run report has status=dry_run."""
        self._save_bp(tmp_base, [
            {"id": "s1", "type": "deterministic", "name": "S1", "run": "echo hi"},
        ])
        result = runner.invoke(app, ["blueprint", "run", "pipe", "--dry-run"])
        assert result.exit_code == 0
        report_dir = tmp_base / ".harness" / "logs" / "blueprints"
        reports = list(report_dir.glob("pipe-*.json"))
        assert len(reports) == 1
        data = json.loads(reports[0].read_text())
        assert data["status"] == "dry_run"

    def test_verbose_shows_stdout(self, tmp_base: Path) -> None:
        """--verbose flag shows step stdout output."""
        self._save_bp(tmp_base, [
            {"id": "s1", "type": "deterministic", "name": "S1", "run": "echo verbose_content"},
        ])
        result = runner.invoke(app, ["blueprint", "run", "pipe", "--verbose"])
        assert result.exit_code == 0
        assert "verbose_content" in result.output
