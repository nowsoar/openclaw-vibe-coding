"""Tests for Phase 4.4: Agentic node executor in Blueprint."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from harness_kit import blueprint as bm
from harness_kit import harness as hm
from harness_kit import skill as sm
from harness_kit.blueprint_executor import (
    BlueprintRunResult,
    StepResult,
    execute_blueprint,
    run_agentic_step,
)
from harness_kit.cli import app
from harness_kit.config import init_harness
from typer.testing import CliRunner

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Initialize a .harness workspace in a temp dir."""
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


def _make_skill(tmp_base: Path, name: str = "test-skill") -> str:
    """Create a minimal skill and return its version."""
    version, _ = sm.save_skill(
        name=name,
        description="Test skill",
        trigger="When testing",
        base=tmp_base,
    )
    return version


def _make_harness(tmp_base: Path, skill_name: str, harness_name: str = "test-harness") -> str:
    """Create a harness referencing a skill."""
    version, _ = hm.save_harness(
        name=harness_name,
        description="Test harness",
        skills=[skill_name],
        base=tmp_base,
    )
    return version


def _fake_llm_response(content: str = "LLM reply"):
    """Return a mock LLMResponse."""
    from harness_kit.llm import LLMResponse
    return LLMResponse(
        content=content,
        model="gpt-4o",
        input_tokens=10,
        output_tokens=5,
        duration=0.1,
    )


# ---------------------------------------------------------------------------
# run_agentic_step — skill reference
# ---------------------------------------------------------------------------


class TestRunAgenticStepSkill:
    def test_success_with_skill(self, tmp_base: Path):
        """run_agentic_step returns success when LLM responds."""
        _make_skill(tmp_base, "my-skill")
        step = {"id": "ai1", "name": "AI Step", "skill": "my-skill"}
        context = {"inputs": {}, "steps": {}}

        with patch("harness_kit.llm.call_llm") as mock_call:
            mock_call.return_value = _fake_llm_response("Hello from LLM")
            result = run_agentic_step(step, context, base=tmp_base)

        assert result.step_id == "ai1"
        assert result.step_type == "agentic"
        assert result.status == "success"
        assert result.output == "Hello from LLM"
        assert result.duration >= 0

    def test_skill_not_found_returns_failed(self, tmp_base: Path):
        """run_agentic_step returns failed when skill doesn't exist."""
        step = {"id": "bad", "skill": "nonexistent-skill"}
        context = {"inputs": {}, "steps": {}}

        result = run_agentic_step(step, context, base=tmp_base)

        assert result.status == "failed"
        assert result.error is not None

    def test_inputs_interpolated_from_context(self, tmp_base: Path):
        """step inputs referencing {{inputs.x}} are interpolated."""
        _make_skill(tmp_base, "chat-skill")
        step = {
            "id": "s",
            "skill": "chat-skill",
            "inputs": {"message": "{{inputs.user_msg}}"},
        }
        context = {"inputs": {"user_msg": "hello world"}, "steps": {}}

        captured_vars: dict = {}

        def fake_build_messages(skill_data, rendered, vars=None):
            captured_vars.update(vars or {})
            return [{"role": "user", "content": "test"}]

        with patch("harness_kit.llm.call_llm") as mock_call, \
             patch("harness_kit.llm.build_messages", side_effect=fake_build_messages):
            mock_call.return_value = _fake_llm_response("ok")
            run_agentic_step(step, context, base=tmp_base)

        assert captured_vars.get("message") == "hello world"

    def test_step_output_propagated(self, tmp_base: Path):
        """Previous step output can be referenced in agentic step inputs."""
        _make_skill(tmp_base, "summary-skill")
        step = {
            "id": "summarize",
            "skill": "summary-skill",
            "inputs": {"text": "{{steps.lint.output}}"},
        }
        context = {
            "inputs": {},
            "steps": {"lint": {"output": "line 1\nline 2", "stderr": "", "exit_code": 0, "status": "success"}},
        }
        captured_vars: dict = {}

        def fake_build_messages(skill_data, rendered, vars=None):
            captured_vars.update(vars or {})
            return [{"role": "user", "content": "test"}]

        with patch("harness_kit.llm.call_llm") as mock_call, \
             patch("harness_kit.llm.build_messages", side_effect=fake_build_messages):
            mock_call.return_value = _fake_llm_response("summary")
            run_agentic_step(step, context, base=tmp_base)

        assert captured_vars.get("text") == "line 1\nline 2"

    def test_llm_exception_returns_failed(self, tmp_base: Path):
        """LLM API error → status=failed."""
        _make_skill(tmp_base, "err-skill")
        step = {"id": "ai_err", "skill": "err-skill"}
        context = {"inputs": {}, "steps": {}}

        with patch("harness_kit.llm.call_llm", side_effect=RuntimeError("API down")):
            result = run_agentic_step(step, context, base=tmp_base)

        assert result.status == "failed"
        assert "API down" in (result.error or "")

    def test_timeout_returns_timeout_status(self, tmp_base: Path):
        """Timeout → status=timeout."""
        _make_skill(tmp_base, "slow-skill")
        step = {"id": "slow", "skill": "slow-skill", "timeout": 1}
        context = {"inputs": {}, "steps": {}}

        import concurrent.futures
        with patch("harness_kit.llm.call_llm", side_effect=Exception("timeout")), \
             patch("concurrent.futures.Future.result", side_effect=concurrent.futures.TimeoutError()):
            result = run_agentic_step(step, context, base=tmp_base)

        # The future.result raises TimeoutError → status=timeout or failed
        assert result.status in ("timeout", "failed")

    def test_no_skill_or_harness_returns_failed(self, tmp_base: Path):
        """Missing both harness and skill → failed."""
        step = {"id": "bad_step"}
        context = {"inputs": {}, "steps": {}}

        result = run_agentic_step(step, context, base=tmp_base)
        assert result.status == "failed"

    def test_call_logged(self, tmp_base: Path):
        """LLM call is recorded in .harness/logs/calls.jsonl."""
        import json
        _make_skill(tmp_base, "log-skill")
        step = {"id": "log", "skill": "log-skill"}
        context = {"inputs": {}, "steps": {}}

        with patch("harness_kit.llm.call_llm") as mock_call:
            mock_call.return_value = _fake_llm_response("logged")
            run_agentic_step(step, context, base=tmp_base)

        log_path = tmp_base / ".harness" / "logs" / "calls.jsonl"
        assert log_path.exists()
        record = json.loads(log_path.read_text().strip().splitlines()[-1])
        assert record["status"] == "success"


# ---------------------------------------------------------------------------
# run_agentic_step — harness reference
# ---------------------------------------------------------------------------


class TestRunAgenticStepHarness:
    def test_success_with_harness(self, tmp_base: Path):
        """run_agentic_step resolves harness → first skill → calls LLM."""
        _make_skill(tmp_base, "h-skill")
        _make_harness(tmp_base, "h-skill", "my-harness")
        step = {"id": "hstep", "harness": "my-harness"}
        context = {"inputs": {}, "steps": {}}

        with patch("harness_kit.llm.call_llm") as mock_call:
            mock_call.return_value = _fake_llm_response("harness reply")
            result = run_agentic_step(step, context, base=tmp_base)

        assert result.status == "success"
        assert result.output == "harness reply"

    def test_harness_not_found_returns_failed(self, tmp_base: Path):
        step = {"id": "bad", "harness": "ghost-harness"}
        context = {"inputs": {}, "steps": {}}
        result = run_agentic_step(step, context, base=tmp_base)
        assert result.status == "failed"

    def test_harness_with_versioned_ref(self, tmp_base: Path):
        """Harness reference with @version is resolved correctly."""
        _make_skill(tmp_base, "versioned-skill")
        version = _make_harness(tmp_base, "versioned-skill", "versioned-harness")
        step = {"id": "vs", "harness": f"versioned-harness@{version}"}
        context = {"inputs": {}, "steps": {}}

        with patch("harness_kit.llm.call_llm") as mock_call:
            mock_call.return_value = _fake_llm_response("versioned")
            result = run_agentic_step(step, context, base=tmp_base)

        assert result.status == "success"


# ---------------------------------------------------------------------------
# Retry behaviour
# ---------------------------------------------------------------------------


class TestAgenticRetry:
    def test_retry_on_rate_limit(self, tmp_base: Path):
        """max_retries=1 retries once on a rate-limit error."""
        _make_skill(tmp_base, "retry-skill")
        step = {"id": "r", "skill": "retry-skill", "max_retries": 1}
        context = {"inputs": {}, "steps": {}}

        call_count = 0

        def flaky_call(messages, config, stream=False):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("rate limit exceeded")
            return _fake_llm_response("retry success")

        with patch("harness_kit.llm.call_llm", side_effect=flaky_call), \
             patch("time.sleep"):  # speed up back-off
            result = run_agentic_step(step, context, base=tmp_base)

        assert result.status == "success"
        assert call_count == 2

    def test_all_retries_exhausted_returns_failed(self, tmp_base: Path):
        """After all retries, returns failed."""
        _make_skill(tmp_base, "always-fail-skill")
        step = {"id": "af", "skill": "always-fail-skill", "max_retries": 2}
        context = {"inputs": {}, "steps": {}}

        with patch("harness_kit.llm.call_llm", side_effect=Exception("rate limit")), \
             patch("time.sleep"):
            result = run_agentic_step(step, context, base=tmp_base)

        assert result.status == "failed"


# ---------------------------------------------------------------------------
# execute_blueprint — agentic steps integrated
# ---------------------------------------------------------------------------


class TestExecuteBlueprintAgentic:
    def _bp(self, steps, **kwargs):
        return {
            "name": "bp",
            "description": "d",
            "inputs": [],
            "steps": steps,
            "outputs": {},
            **kwargs,
        }

    def test_agentic_step_executes(self, tmp_base: Path):
        """Agentic step now executes (no longer skipped)."""
        _make_skill(tmp_base, "chat")
        bp = self._bp([{"id": "ai", "type": "agentic", "skill": "chat"}])

        with patch("harness_kit.llm.call_llm") as mock_call:
            mock_call.return_value = _fake_llm_response("good output")
            result = execute_blueprint(bp, {}, base=tmp_base)

        assert result.steps[0].status == "success"
        assert result.steps[0].output == "good output"
        assert result.status == "success"

    def test_agentic_output_used_by_next_step(self, tmp_base: Path):
        """Output from an agentic step is interpolated into subsequent steps."""
        _make_skill(tmp_base, "gen-skill")
        bp = self._bp(
            steps=[
                {"id": "gen", "type": "agentic", "skill": "gen-skill"},
                {"id": "echo", "type": "deterministic", "run": "echo {{steps.gen.output}}"},
            ],
            outputs={"result": "{{steps.gen.output}}"},
        )

        with patch("harness_kit.llm.call_llm") as mock_call:
            mock_call.return_value = _fake_llm_response("generated_text")
            result = execute_blueprint(bp, {}, base=tmp_base)

        assert "generated_text" in result.outputs.get("result", "")
        assert result.steps[1].status == "success"

    def test_agentic_failure_triggers_on_fail_stop(self, tmp_base: Path):
        """Failed agentic step with on_fail=stop stops the pipeline."""
        _make_skill(tmp_base, "fail-skill")
        bp = self._bp([
            {"id": "ai_bad", "type": "agentic", "skill": "fail-skill", "on_fail": "stop"},
            {"id": "after", "type": "deterministic", "run": "echo should-not-run"},
        ])

        with patch("harness_kit.llm.call_llm", side_effect=RuntimeError("boom")):
            result = execute_blueprint(bp, {}, base=tmp_base)

        assert result.status == "stopped"
        assert result.steps[1].status == "skipped"

    def test_agentic_failure_with_on_fail_continue(self, tmp_base: Path):
        """Failed agentic step with on_fail=continue lets pipeline proceed."""
        _make_skill(tmp_base, "cont-skill")
        bp = self._bp([
            {"id": "ai_ok", "type": "agentic", "skill": "cont-skill", "on_fail": "continue"},
            {"id": "next", "type": "deterministic", "run": "echo continued"},
        ])

        with patch("harness_kit.llm.call_llm", side_effect=RuntimeError("oops")):
            result = execute_blueprint(bp, {}, base=tmp_base)

        statuses = {r.step_id: r.status for r in result.steps}
        assert statuses["ai_ok"] == "failed"
        assert statuses["next"] == "success"
        assert result.status == "failed"  # overall failed because a step failed

    def test_mixed_deterministic_and_agentic(self, tmp_base: Path):
        """Pipeline with both deterministic and agentic steps runs successfully."""
        _make_skill(tmp_base, "mixed-skill")
        bp = self._bp([
            {"id": "prep", "type": "deterministic", "run": "echo ready"},
            {"id": "ai", "type": "agentic", "skill": "mixed-skill"},
            {"id": "done", "type": "deterministic", "run": "echo done"},
        ])

        with patch("harness_kit.llm.call_llm") as mock_call:
            mock_call.return_value = _fake_llm_response("ai result")
            result = execute_blueprint(bp, {}, base=tmp_base)

        assert result.status == "success"
        assert all(r.status == "success" for r in result.steps)

    def test_dry_run_agentic_not_called(self, tmp_base: Path):
        """dry_run skips actual LLM call for agentic steps."""
        _make_skill(tmp_base, "dry-skill")
        bp = self._bp([{"id": "ai", "type": "agentic", "skill": "dry-skill"}])

        with patch("harness_kit.llm.call_llm") as mock_call:
            result = execute_blueprint(bp, {}, dry_run=True, base=tmp_base)

        mock_call.assert_not_called()
        assert result.status == "dry_run"
        assert "dry-run" in result.steps[0].output

    def test_overall_status_failed_when_agentic_fails(self, tmp_base: Path):
        """Overall status is 'failed' when an agentic step fails (with on_fail=continue)."""
        _make_skill(tmp_base, "fail2-skill")
        bp = self._bp([
            {"id": "ai", "type": "agentic", "skill": "fail2-skill", "on_fail": "continue"},
        ])

        with patch("harness_kit.llm.call_llm", side_effect=RuntimeError("err")):
            result = execute_blueprint(bp, {}, base=tmp_base)

        assert result.status == "failed"


# ---------------------------------------------------------------------------
# CLI integration — harnesskit blueprint run with agentic step
# ---------------------------------------------------------------------------


class TestBlueprintRunCLIAgentic:
    def test_agentic_step_runs_via_cli(self, tmp_base: Path):
        """CLI blueprint run executes an agentic step successfully."""
        _make_skill(tmp_base, "cli-skill")
        bp = {
            "name": "agentic-pipeline",
            "description": "Test agentic CLI",
            "inputs": [],
            "steps": [{"id": "ai", "type": "agentic", "skill": "cli-skill"}],
            "outputs": {},
        }
        bm.save_blueprint_from_dict(bp, tmp_base)

        with patch("harness_kit.llm.call_llm") as mock_call:
            mock_call.return_value = _fake_llm_response("cli output")
            result = runner.invoke(app, ["blueprint", "run", "agentic-pipeline"])

        assert result.exit_code == 0
        assert "✓" in result.output

    def test_agentic_step_failure_exits_nonzero(self, tmp_base: Path):
        """Failed agentic step with on_fail=stop exits nonzero."""
        _make_skill(tmp_base, "cli-fail-skill")
        bp = {
            "name": "fail-pipeline",
            "description": "Test fail",
            "inputs": [],
            "steps": [{"id": "ai", "type": "agentic", "skill": "cli-fail-skill", "on_fail": "stop"}],
            "outputs": {},
        }
        bm.save_blueprint_from_dict(bp, tmp_base)

        with patch("harness_kit.llm.call_llm", side_effect=RuntimeError("down")):
            result = runner.invoke(app, ["blueprint", "run", "fail-pipeline"])

        assert result.exit_code != 0

    def test_agentic_dry_run_via_cli(self, tmp_base: Path):
        """CLI --dry-run does not invoke LLM."""
        _make_skill(tmp_base, "cli-dry-skill")
        bp = {
            "name": "dry-pipeline",
            "description": "Test dry",
            "inputs": [],
            "steps": [{"id": "ai", "type": "agentic", "skill": "cli-dry-skill"}],
            "outputs": {},
        }
        bm.save_blueprint_from_dict(bp, tmp_base)

        with patch("harness_kit.llm.call_llm") as mock_call:
            result = runner.invoke(app, ["blueprint", "run", "dry-pipeline", "--dry-run"])

        mock_call.assert_not_called()
        assert result.exit_code == 0
