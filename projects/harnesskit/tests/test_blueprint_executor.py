"""Tests for Phase 4.3: Blueprint deterministic node executor."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit import blueprint as bm
from harness_kit.blueprint_executor import (
    StepResult,
    BlueprintRunResult,
    interpolate_variables,
    run_deterministic_step,
    execute_blueprint,
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
        "description": "Test pipeline",
        "inputs": [],
        "steps": steps,
        "outputs": {},
        **kwargs,
    }


# ---------------------------------------------------------------------------
# interpolate_variables
# ---------------------------------------------------------------------------


class TestInterpolateVariables:
    def test_inputs_variable(self):
        ctx = {"inputs": {"file_path": "/tmp/foo.py"}, "steps": {}}
        assert interpolate_variables("flake8 {{inputs.file_path}}", ctx) == "flake8 /tmp/foo.py"

    def test_step_output(self):
        ctx = {
            "inputs": {},
            "steps": {"step1": {"output": "hello\n", "stderr": "", "exit_code": 0, "status": "success"}},
        }
        assert interpolate_variables("result: {{steps.step1.output}}", ctx) == "result: hello\n"

    def test_step_exit_code(self):
        ctx = {"inputs": {}, "steps": {"s": {"output": "", "stderr": "", "exit_code": 42, "status": "failed"}}}
        assert interpolate_variables("code={{steps.s.exit_code}}", ctx) == "code=42"

    def test_env_variable(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MY_TOKEN", "abc123")
        ctx = {"inputs": {}, "steps": {}}
        assert interpolate_variables("token={{env.MY_TOKEN}}", ctx) == "token=abc123"

    def test_missing_env_variable(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("NO_SUCH_ENV_VAR", raising=False)
        ctx = {"inputs": {}, "steps": {}}
        # Should leave placeholder unchanged when env var missing
        result = interpolate_variables("x={{env.NO_SUCH_ENV_VAR}}", ctx)
        assert result == "x={{env.NO_SUCH_ENV_VAR}}"

    def test_unknown_path_left_unchanged(self):
        ctx = {"inputs": {}, "steps": {}}
        template = "{{steps.nonexistent.output}}"
        assert interpolate_variables(template, ctx) == template

    def test_multiple_vars(self):
        ctx = {"inputs": {"a": "hello", "b": "world"}, "steps": {}}
        assert interpolate_variables("{{inputs.a}} {{inputs.b}}", ctx) == "hello world"

    def test_nested_dict(self):
        ctx = {"inputs": {}, "steps": {"s1": {"output": "ok", "exit_code": 0, "stderr": "", "status": "success"}}}
        assert interpolate_variables("out={{steps.s1.output}}", ctx) == "out=ok"

    def test_no_placeholders(self):
        assert interpolate_variables("echo hello", {}) == "echo hello"


# ---------------------------------------------------------------------------
# run_deterministic_step
# ---------------------------------------------------------------------------


class TestRunDeterministicStep:
    def test_success_echo(self):
        step = {"id": "greet", "name": "Greeting", "run": "echo hello"}
        ctx = {"inputs": {}, "steps": {}}
        res = run_deterministic_step(step, ctx)
        assert res.status == "success"
        assert "hello" in res.output
        assert res.exit_code == 0
        assert res.duration >= 0

    def test_failure_exit_code(self):
        step = {"id": "bad", "name": "Bad cmd", "run": "exit 2", "timeout": 5}
        ctx = {"inputs": {}, "steps": {}}
        res = run_deterministic_step(step, ctx)
        assert res.status == "failed"
        assert res.exit_code == 2

    def test_captures_stderr(self):
        step = {"id": "err", "name": "Stderr", "run": "echo error-msg >&2; exit 1"}
        ctx = {"inputs": {}, "steps": {}}
        res = run_deterministic_step(step, ctx)
        assert res.status == "failed"
        assert "error-msg" in res.stderr

    def test_interpolates_command(self):
        step = {"id": "echo_input", "run": "echo {{inputs.word}}"}
        ctx = {"inputs": {"word": "pytest"}, "steps": {}}
        res = run_deterministic_step(step, ctx)
        assert res.status == "success"
        assert "pytest" in res.output

    def test_timeout(self):
        # sleep for 5s but timeout is 1s
        step = {"id": "slow", "run": "sleep 5", "timeout": 1}
        ctx = {"inputs": {}, "steps": {}}
        res = run_deterministic_step(step, ctx)
        assert res.status == "timeout"
        assert "1s" in res.error
        assert res.exit_code is None

    def test_default_timeout_used(self):
        # No timeout key — defaults to 60, command is fast so it succeeds
        step = {"id": "fast", "run": "echo ok"}
        ctx = {"inputs": {}, "steps": {}}
        res = run_deterministic_step(step, ctx)
        assert res.status == "success"


# ---------------------------------------------------------------------------
# execute_blueprint
# ---------------------------------------------------------------------------


class TestExecuteBlueprint:
    def test_single_step_success(self):
        bp = _simple_blueprint([{"id": "s1", "type": "deterministic", "run": "echo ok"}])
        result = execute_blueprint(bp, {})
        assert result.status == "success"
        assert len(result.steps) == 1
        assert result.steps[0].status == "success"

    def test_two_steps_sequential(self):
        bp = _simple_blueprint([
            {"id": "a", "type": "deterministic", "run": "echo step-a"},
            {"id": "b", "type": "deterministic", "run": "echo step-b"},
        ])
        result = execute_blueprint(bp, {})
        assert result.status == "success"
        assert [r.step_id for r in result.steps] == ["a", "b"]
        assert all(r.status == "success" for r in result.steps)

    def test_step_output_propagated(self):
        bp = _simple_blueprint(
            steps=[
                {"id": "gen", "type": "deterministic", "run": "printf hello"},
                {"id": "use", "type": "deterministic", "run": "echo {{steps.gen.output}}"},
            ],
            outputs={"word": "{{steps.gen.output}}"},
        )
        result = execute_blueprint(bp, {})
        assert result.status == "success"
        assert "hello" in result.outputs.get("word", "")

    def test_on_fail_stop(self):
        bp = _simple_blueprint([
            {"id": "bad", "type": "deterministic", "run": "exit 1", "on_fail": "stop"},
            {"id": "skipped", "type": "deterministic", "run": "echo should-not-run"},
        ])
        result = execute_blueprint(bp, {})
        assert result.status == "stopped"
        assert result.stop_reason is not None
        assert result.steps[1].status == "skipped"

    def test_on_fail_continue(self):
        bp = _simple_blueprint([
            {"id": "bad", "type": "deterministic", "run": "exit 1", "on_fail": "continue"},
            {"id": "ok", "type": "deterministic", "run": "echo continued"},
        ])
        result = execute_blueprint(bp, {})
        # status is "failed" because a deterministic step failed, but we continued
        assert result.status == "failed"
        # Both steps ran
        statuses = {r.step_id: r.status for r in result.steps}
        assert statuses["bad"] == "failed"
        assert statuses["ok"] == "success"

    def test_on_fail_goto(self):
        bp = _simple_blueprint([
            {"id": "step1", "type": "deterministic", "run": "exit 1", "on_fail": "goto:step3"},
            {"id": "step2", "type": "deterministic", "run": "echo should-be-skipped"},
            {"id": "step3", "type": "deterministic", "run": "echo recovery"},
        ])
        result = execute_blueprint(bp, {})
        step_ids = [r.step_id for r in result.steps]
        # step1 runs, step2 does NOT run (we jumped over it), step3 runs
        assert "step1" in step_ids
        assert "step3" in step_ids
        # step2 should not appear or appear as skipped (not as success/failed)
        step2_results = [r for r in result.steps if r.step_id == "step2"]
        for r in step2_results:
            assert r.status != "success"

    def test_on_fail_goto_invalid_target(self):
        bp = _simple_blueprint([
            {"id": "bad", "type": "deterministic", "run": "exit 1", "on_fail": "goto:nonexistent"},
        ])
        result = execute_blueprint(bp, {})
        assert result.status == "stopped"
        assert "nonexistent" in (result.stop_reason or "")

    def test_agentic_step_skipped(self):
        bp = _simple_blueprint([
            {"id": "ai_step", "type": "agentic", "harness": "some-harness@v0.1.0"},
        ])
        result = execute_blueprint(bp, {})
        assert result.steps[0].status == "skipped"
        assert "Phase 4.4" in result.steps[0].output

    def test_input_variable_interpolated(self):
        bp = {
            "name": "greet",
            "description": "Greeting pipeline",
            "inputs": [{"name": "name", "required": True}],
            "steps": [{"id": "say", "type": "deterministic", "run": "echo hello {{inputs.name}}"}],
            "outputs": {"greeting": "{{steps.say.output}}"},
        }
        result = execute_blueprint(bp, {"name": "World"})
        assert "World" in result.outputs.get("greeting", "")

    def test_input_default_applied(self):
        bp = {
            "name": "bp",
            "description": "test",
            "inputs": [{"name": "lang", "required": False, "default": "python"}],
            "steps": [{"id": "s", "type": "deterministic", "run": "echo {{inputs.lang}}"}],
            "outputs": {},
        }
        result = execute_blueprint(bp, {})
        assert "python" in result.steps[0].output

    def test_dry_run_does_not_execute(self):
        """dry_run should not actually run the command."""
        bp = _simple_blueprint([
            {"id": "del", "type": "deterministic", "run": "rm -rf /nonexistent_path_xyz"},
        ])
        result = execute_blueprint(bp, {}, dry_run=True)
        assert result.status == "dry_run"
        assert result.steps[0].status == "dry_run"
        assert "dry-run" in result.steps[0].output

    def test_dry_run_agentic(self):
        bp = _simple_blueprint([
            {"id": "ai", "type": "agentic", "harness": "h@v0.1.0"},
        ])
        result = execute_blueprint(bp, {}, dry_run=True)
        assert result.status == "dry_run"
        assert "dry-run" in result.steps[0].output

    def test_start_step_skips_earlier(self):
        bp = _simple_blueprint([
            {"id": "s1", "type": "deterministic", "run": "echo first"},
            {"id": "s2", "type": "deterministic", "run": "echo second"},
            {"id": "s3", "type": "deterministic", "run": "echo third"},
        ])
        result = execute_blueprint(bp, {}, start_step="s2")
        statuses = {r.step_id: r.status for r in result.steps}
        assert statuses["s1"] == "skipped"
        assert statuses["s2"] == "success"
        assert statuses["s3"] == "success"

    def test_start_step_unknown(self):
        bp = _simple_blueprint([{"id": "s1", "type": "deterministic", "run": "echo hi"}])
        result = execute_blueprint(bp, {}, start_step="bad_id")
        assert result.status == "stopped"
        assert "bad_id" in (result.stop_reason or "")

    def test_outputs_resolved(self):
        bp = _simple_blueprint(
            steps=[{"id": "out_step", "type": "deterministic", "run": "printf world"}],
            outputs={"result": "{{steps.out_step.output}}"},
        )
        result = execute_blueprint(bp, {})
        assert result.outputs["result"] == "world"

    def test_timeout_step_triggers_stop(self):
        bp = _simple_blueprint([
            {"id": "slow", "type": "deterministic", "run": "sleep 5", "timeout": 1, "on_fail": "stop"},
            {"id": "after", "type": "deterministic", "run": "echo after"},
        ])
        result = execute_blueprint(bp, {})
        assert result.status == "stopped"
        assert result.steps[0].status == "timeout"
        assert result.steps[1].status == "skipped"

    def test_all_steps_empty(self):
        bp = _simple_blueprint(steps=[])
        result = execute_blueprint(bp, {})
        assert result.status == "success"
        assert result.steps == []

    def test_step_failure_status_failed(self):
        """When on_fail=continue, overall status is 'failed'."""
        bp = _simple_blueprint([
            {"id": "bad", "type": "deterministic", "run": "exit 1", "on_fail": "continue"},
        ])
        result = execute_blueprint(bp, {})
        assert result.status == "failed"


# ---------------------------------------------------------------------------
# CLI: harnesskit blueprint run
# ---------------------------------------------------------------------------


class TestBlueprintRunCLI:
    def _save_bp(self, tmp_base: Path, bp: dict, name: str = "test-pipeline") -> None:
        bp["name"] = name
        bm.save_blueprint_from_dict(bp, tmp_base)

    def test_run_single_success(self, tmp_base: Path):
        bp = {
            "name": "p",
            "description": "d",
            "inputs": [],
            "steps": [{"id": "s1", "type": "deterministic", "run": "echo cli-ok"}],
            "outputs": {},
        }
        self._save_bp(tmp_base, bp, "p")
        result = runner.invoke(app, ["blueprint", "run", "p"])
        assert result.exit_code == 0
        assert "✓" in result.output

    def test_run_dry_run(self, tmp_base: Path):
        bp = {
            "name": "p2",
            "description": "d",
            "inputs": [],
            "steps": [{"id": "s1", "type": "deterministic", "run": "echo dry"}],
            "outputs": {},
        }
        self._save_bp(tmp_base, bp, "p2")
        result = runner.invoke(app, ["blueprint", "run", "p2", "--dry-run"])
        assert result.exit_code == 0
        assert "dry" in result.output.lower()

    def test_run_with_var(self, tmp_base: Path):
        bp = {
            "name": "p3",
            "description": "d",
            "inputs": [{"name": "msg", "required": True}],
            "steps": [{"id": "s", "type": "deterministic", "run": "echo {{inputs.msg}}"}],
            "outputs": {},
        }
        self._save_bp(tmp_base, bp, "p3")
        result = runner.invoke(app, ["blueprint", "run", "p3", "--var", "msg=greetings"])
        assert result.exit_code == 0

    def test_run_missing_required_input(self, tmp_base: Path):
        bp = {
            "name": "p4",
            "description": "d",
            "inputs": [{"name": "required_arg", "required": True}],
            "steps": [{"id": "s", "type": "deterministic", "run": "echo {{inputs.required_arg}}"}],
            "outputs": {},
        }
        self._save_bp(tmp_base, bp, "p4")
        result = runner.invoke(app, ["blueprint", "run", "p4"])
        assert result.exit_code != 0
        assert "required_arg" in result.output

    def test_run_failure_exits_nonzero(self, tmp_base: Path):
        bp = {
            "name": "p5",
            "description": "d",
            "inputs": [],
            "steps": [{"id": "bad", "type": "deterministic", "run": "exit 1", "on_fail": "stop"}],
            "outputs": {},
        }
        self._save_bp(tmp_base, bp, "p5")
        result = runner.invoke(app, ["blueprint", "run", "p5"])
        assert result.exit_code != 0

    def test_run_nonexistent_blueprint(self, tmp_base: Path):
        result = runner.invoke(app, ["blueprint", "run", "no-such-bp"])
        assert result.exit_code != 0

    def test_run_on_fail_continue_exits_nonzero(self, tmp_base: Path):
        """on_fail=continue still exits nonzero because overall status is 'failed'."""
        bp = {
            "name": "p6",
            "description": "d",
            "inputs": [],
            "steps": [
                {"id": "bad", "type": "deterministic", "run": "exit 1", "on_fail": "continue"},
                {"id": "ok", "type": "deterministic", "run": "echo survived"},
            ],
            "outputs": {},
        }
        self._save_bp(tmp_base, bp, "p6")
        result = runner.invoke(app, ["blueprint", "run", "p6"])
        assert result.exit_code != 0

    def test_run_verbose_shows_stdout(self, tmp_base: Path):
        bp = {
            "name": "p7",
            "description": "d",
            "inputs": [],
            "steps": [{"id": "s", "type": "deterministic", "run": "echo verbose-output"}],
            "outputs": {},
        }
        self._save_bp(tmp_base, bp, "p7")
        result = runner.invoke(app, ["blueprint", "run", "p7", "--verbose"])
        assert result.exit_code == 0
        assert "verbose-output" in result.output

    def test_run_start_step(self, tmp_base: Path):
        bp = {
            "name": "p8",
            "description": "d",
            "inputs": [],
            "steps": [
                {"id": "s1", "type": "deterministic", "run": "echo first"},
                {"id": "s2", "type": "deterministic", "run": "echo second"},
            ],
            "outputs": {},
        }
        self._save_bp(tmp_base, bp, "p8")
        result = runner.invoke(app, ["blueprint", "run", "p8", "--step", "s2"])
        assert result.exit_code == 0

    def test_run_invalid_var_format(self, tmp_base: Path):
        bp = {
            "name": "p9",
            "description": "d",
            "inputs": [],
            "steps": [{"id": "s", "type": "deterministic", "run": "echo hi"}],
            "outputs": {},
        }
        self._save_bp(tmp_base, bp, "p9")
        result = runner.invoke(app, ["blueprint", "run", "p9", "--var", "badformat"])
        assert result.exit_code != 0
