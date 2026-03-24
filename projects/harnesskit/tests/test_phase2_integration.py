"""Phase 2.6 — End-to-end integration tests for the full Phase 2 Skill workflow.

Covers:
  init → save prompts → add rules → create context → save skill → run (mocked LLM)
  → check results → check logs → performance baselines
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from harness_kit.cli import app
from harness_kit import call_logger as cl
from harness_kit.config import init_harness
from harness_kit import skill as sm
from harness_kit import prompt as pm
from harness_kit import rule as rm
from harness_kit import context as ctxm

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Initialised .harness workspace in tmp_path."""
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


@pytest.fixture()
def full_workspace(workspace: Path) -> Path:
    """Workspace with all Phase 1 + Phase 2 assets wired together."""
    # System prompt
    pm.save_prompt(
        name="code-reviewer-system",
        content=(
            "You are a senior {{language}} engineer specialising in code review. "
            "Identify issues and return a clear list."
        ),
        description="System prompt for code reviewer",
        tags=["code", "review"],
        base=workspace,
    )
    # User prompt
    pm.save_prompt(
        name="code-reviewer-user",
        content="Please review the following code:\n{{code}}",
        description="User prompt for code reviewer",
        base=workspace,
    )
    # Hard rule
    rm.save_rule(
        name="no-speculation",
        rule_type="hard",
        description="Do not speculate — only report confirmed issues",
        check_type="regex",
        pattern=r"我猜测|可能是|I think|probably",
        fix_hint="Remove speculative language; only report confirmed issues",
        base=workspace,
    )
    # Soft rule
    rm.save_rule(
        name="output-json",
        rule_type="soft",
        description="Always return output as valid JSON",
        check_type="regex",
        pattern=r".",
        base=workspace,
    )
    # Context template
    ctxm.save_context(
        name="review-ctx",
        template="Review the following {{language}} code:\n{{code}}\n",
        slots=[
            {"name": "language", "required": True},
            {"name": "code", "required": True},
        ],
        description="Code review context",
        base=workspace,
    )

    # Full skill wiring all assets
    sm.save_skill(
        name="code-reviewer",
        description="Reviews code and outputs a list of issues",
        trigger="When code needs review",
        inputs=[
            {"name": "code", "type": "string", "required": True},
            {"name": "language", "type": "string", "default": "auto"},
        ],
        outputs=[{"name": "issues", "type": "array"}],
        assets={
            "prompts": {
                "system": "code-reviewer-system",
                "user": "code-reviewer-user",
            },
            "rules": ["no-speculation", "output-json"],
            "context": "review-ctx",
        },
        examples=[
            {
                "input": {"code": "def foo(): pass", "language": "python"},
                "expected_contains": ["缺少实现"],
            }
        ],
        changelog="Initial version",
        base=workspace,
    )
    return workspace


def _mock_llm_response(content: str = '{"issues": []}') -> MagicMock:
    """Build a minimal mocked OpenAI response object."""
    usage = MagicMock()
    usage.prompt_tokens = 120
    usage.completion_tokens = 40
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    resp.model = "gpt-4o"
    resp.id = "chatcmpl-test"
    return resp


def invoke(*args: str) -> tuple[int, str]:
    result = runner.invoke(app, list(args))
    return result.exit_code, result.output


# ---------------------------------------------------------------------------
# Test: full happy-path end-to-end workflow
# ---------------------------------------------------------------------------


class TestFullSkillWorkflow:
    """
    Complete Phase 2 end-to-end:
      init → save prompts → add rules → save context → save skill
      → validate refs → run (mocked) → check output → check log
    """

    def test_workspace_assets_exist(self, full_workspace: Path) -> None:
        """All Phase 1 assets were created correctly."""
        code, out = invoke("prompt", "list")
        assert code == 0
        # Rich may truncate long names in the table; check for the common prefix
        assert "code-reviewer" in out

        code, out = invoke("rule", "list")
        assert code == 0
        assert "no-speculation" in out
        assert "output-json" in out

        code, out = invoke("context", "list")
        assert code == 0
        assert "review-ctx" in out

    def test_skill_was_saved(self, full_workspace: Path) -> None:
        code, out = invoke("skill", "list")
        assert code == 0
        assert "code-reviewer" in out

    def test_skill_validate_passes(self, full_workspace: Path) -> None:
        """All asset references in the skill resolve correctly."""
        code, out = invoke("skill", "validate", "code-reviewer")
        assert code == 0
        assert "valid" in out.lower() or "✓" in out or "All references" in out

    def test_skill_show_contains_all_sections(self, full_workspace: Path) -> None:
        code, out = invoke("skill", "show", "code-reviewer")
        assert code == 0
        assert "code-reviewer" in out
        assert "Reviews code" in out
        # inputs/outputs
        assert "code" in out
        assert "language" in out

    def test_skill_deps_lists_all_assets(self, full_workspace: Path) -> None:
        code, out = invoke("skill", "deps", "code-reviewer")
        assert code == 0
        assert "code-reviewer-system" in out
        assert "code-reviewer-user" in out
        assert "no-speculation" in out
        assert "output-json" in out
        assert "review-ctx" in out

    def test_skill_dry_run_assembles_messages(self, full_workspace: Path) -> None:
        code, out = invoke(
            "skill", "run", "code-reviewer",
            "--var", "code=def foo(): pass",
            "--var", "language=python",
            "--dry-run",
        )
        assert code == 0
        # Should show assembled messages without calling LLM
        assert "dry" in out.lower() or "Assembled" in out or "messages" in out.lower()

    def test_skill_run_with_mocked_llm(
        self, full_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Full run: assembles prompt → calls (mocked) LLM → shows output → logs call."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
        response_content = '{"issues": [{"line": 1, "message": "缺少实现", "severity": "warning"}]}'

        with patch("openai.OpenAI") as mock_cls:
            client = MagicMock()
            mock_cls.return_value = client
            client.chat.completions.create.return_value = _mock_llm_response(
                response_content
            )
            result = runner.invoke(
                app,
                ["skill", "run", "code-reviewer",
                 "--var", "code=def foo(): pass",
                 "--var", "language=python"],
            )

        assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"
        assert response_content in result.output or "缺少实现" in result.output

        # Verify call log was written
        log_file = full_workspace / ".harness" / "logs" / "calls.jsonl"
        assert log_file.exists()
        record = json.loads(log_file.read_text().strip())
        assert record["skill"] == "code-reviewer"
        assert record["status"] == "success"
        assert record["input_tokens"] == 120
        assert record["output_tokens"] == 40
        assert record["total_tokens"] == 160

    def test_skill_run_hard_rule_catches_violation(
        self, full_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Hard rule blocks speculative output in strict mode."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
        bad_output = "我猜测这里有一个 bug。"

        with patch("openai.OpenAI") as mock_cls:
            client = MagicMock()
            mock_cls.return_value = client
            client.chat.completions.create.return_value = _mock_llm_response(bad_output)

            result = runner.invoke(
                app,
                ["skill", "run", "code-reviewer",
                 "--var", "code=x=1",
                 "--check-rules", "strict"],
            )

        assert result.exit_code != 0
        assert "no-speculation" in result.output or "Rule Violations" in result.output

    def test_skill_run_soft_rule_injected_to_prompt(
        self, full_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dry-run output should contain soft rule instruction in system prompt."""
        code, out = invoke(
            "skill", "run", "code-reviewer",
            "--var", "code=x=1",
            "--dry-run",
        )
        assert code == 0
        # The soft rule description should appear in assembled messages
        assert "output-json" in out or "JSON" in out or "valid JSON" in out

    def test_logs_tail_after_run(
        self, full_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Logs tail shows the call after a successful run."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")

        with patch("openai.OpenAI") as mock_cls:
            client = MagicMock()
            mock_cls.return_value = client
            client.chat.completions.create.return_value = _mock_llm_response()
            runner.invoke(
                app,
                ["skill", "run", "code-reviewer",
                 "--var", "code=pass"],
            )

        code, out = invoke("logs", "tail", "--n", "5")
        assert code == 0
        # Rich may truncate "code-reviewer" in the table; check for prefix
        assert "code-review" in out

    def test_doctor_passes_after_full_phase2_setup(self, full_workspace: Path) -> None:
        """Doctor reports no broken references after full Phase 2 setup."""
        code, out = invoke("doctor")
        assert code == 0
        assert "No circular references" in out
        assert "Summary" in out

    def test_skill_version_history(self, full_workspace: Path) -> None:
        """Saving the skill again increments the version."""
        sm.save_skill(
            name="code-reviewer",
            description="Updated reviewer",
            base=full_workspace,
        )
        versions = sm.list_versions("code-reviewer", full_workspace)
        assert "v0.0.1" in versions
        assert "v0.0.2" in versions

    def test_skill_tag_and_retrieve_by_tag(self, full_workspace: Path) -> None:
        """Tag the current version and load skill by tag alias."""
        code, out = invoke("skill", "tag", "code-reviewer", "--name", "production")
        assert code == 0
        assert "production" in out

        code, out = invoke("skill", "show", "code-reviewer@production")
        assert code == 0
        assert "code-reviewer" in out

    def test_skill_clone_creates_new_skill(self, full_workspace: Path) -> None:
        code, out = invoke("skill", "clone", "code-reviewer", "code-reviewer-v2")
        assert code == 0
        assert "code-reviewer-v2" in out

        code2, out2 = invoke("skill", "list")
        assert code2 == 0
        # Rich may truncate long skill names; verify both are listed
        assert "code-reviewer" in out2
        # The list should have at least 2 entries (original + clone)
        assert out2.count("v0.0.1") >= 2

    def test_cloned_skill_can_run(
        self, full_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cloned skill inherits assets and can run successfully."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
        invoke("skill", "clone", "code-reviewer", "code-reviewer-clone")

        with patch("openai.OpenAI") as mock_cls:
            client = MagicMock()
            mock_cls.return_value = client
            client.chat.completions.create.return_value = _mock_llm_response("OK")

            result = runner.invoke(
                app,
                ["skill", "run", "code-reviewer-clone",
                 "--var", "code=x=1"],
            )

        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# Test: error paths in Phase 2 workflow
# ---------------------------------------------------------------------------


class TestPhase2ErrorPaths:

    def test_run_skill_missing_required_input(self, full_workspace: Path) -> None:
        result = runner.invoke(app, ["skill", "run", "code-reviewer"])
        assert result.exit_code != 0
        assert "code" in result.output.lower() or "required" in result.output.lower()

    def test_run_nonexistent_skill(self, workspace: Path) -> None:
        result = runner.invoke(app, ["skill", "run", "ghost-skill", "--var", "x=y"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "ghost-skill" in result.output

    def test_validate_skill_with_broken_ref(self, workspace: Path) -> None:
        """A skill referencing a missing prompt should fail validation."""
        sm.save_skill(
            name="broken-skill",
            description="Skill with missing prompt",
            inputs=[],
            outputs=[],
            assets={"prompts": {"system": "ghost-prompt"}},
            base=workspace,
        )
        code, out = invoke("skill", "validate", "broken-skill")
        assert code != 0
        assert "ghost-prompt" in out or "not found" in out.lower()

    def test_no_api_key_gives_clear_error(
        self, full_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = runner.invoke(
            app,
            ["skill", "run", "code-reviewer",
             "--var", "code=x=1"],
        )
        assert result.exit_code != 0
        assert "api" in result.output.lower() or "key" in result.output.lower()

    def test_clone_to_existing_name_fails(self, full_workspace: Path) -> None:
        # Create another skill to collide with
        sm.save_skill(name="existing", description="x", base=full_workspace)
        code, out = invoke("skill", "clone", "code-reviewer", "existing")
        assert code != 0
        assert "exists" in out.lower() or "already" in out.lower()

    def test_tag_nonexistent_skill_fails(self, workspace: Path) -> None:
        code, out = invoke("skill", "tag", "ghost", "--name", "prod")
        assert code != 0


# ---------------------------------------------------------------------------
# Test: violation logging end-to-end
# ---------------------------------------------------------------------------


class TestViolationLogging:

    def test_violation_recorded_in_log(
        self, full_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Hard rule violation is recorded in calls.jsonl with violations field."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")

        with patch("openai.OpenAI") as mock_cls:
            client = MagicMock()
            mock_cls.return_value = client
            client.chat.completions.create.return_value = _mock_llm_response(
                "我猜测这是一个问题"
            )
            runner.invoke(
                app,
                ["skill", "run", "code-reviewer",
                 "--var", "code=x=1",
                 "--check-rules", "lenient"],  # lenient: log but don't fail
            )

        log_file = full_workspace / ".harness" / "logs" / "calls.jsonl"
        records = [json.loads(line) for line in log_file.read_text().splitlines() if line]
        assert len(records) >= 1
        last = records[-1]
        assert last.get("violation_count", 0) >= 1
        assert "violations" in last

    def test_rule_stats_shows_violations(
        self, full_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """rule stats command reflects violations recorded in log."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")

        # Run twice to record two violations
        for _ in range(2):
            with patch("openai.OpenAI") as mock_cls:
                client = MagicMock()
                mock_cls.return_value = client
                client.chat.completions.create.return_value = _mock_llm_response(
                    "I think this might be wrong"
                )
                runner.invoke(
                    app,
                    ["skill", "run", "code-reviewer",
                     "--var", "code=pass",
                     "--check-rules", "lenient"],
                )

        code, out = invoke("rule", "stats")
        assert code == 0
        assert "no-speculation" in out


# ---------------------------------------------------------------------------
# Test: performance baselines
# ---------------------------------------------------------------------------


class TestPerformance:
    """
    Lightweight performance baselines — verifies that core local operations
    (no LLM calls) complete within reasonable time bounds.
    """

    def test_log_write_100_records_under_1s(self, workspace: Path) -> None:
        """Writing 100 call-log records should complete in under 1 second."""
        start = time.monotonic()
        for i in range(100):
            cl.log_call(
                skill=f"skill-{i}",
                model="gpt-4o",
                input_tokens=i,
                output_tokens=i // 2,
                duration=0.5,
                status="success",
                base=workspace,
            )
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"100 log writes took {elapsed:.2f}s (expected < 1s)"

        log_file = workspace / ".harness" / "logs" / "calls.jsonl"
        lines = [l for l in log_file.read_text().splitlines() if l.strip()]
        assert len(lines) == 100

    def test_skill_save_50_versions_under_2s(self, workspace: Path) -> None:
        """Saving 50 skill versions should complete in under 2 seconds."""
        start = time.monotonic()
        for i in range(50):
            sm.save_skill(
                name="perf-skill",
                description=f"Version {i}",
                inputs=[{"name": "x", "type": "string", "required": True}],
                outputs=[{"name": "y", "type": "string"}],
                base=workspace,
            )
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"50 skill saves took {elapsed:.2f}s (expected < 2s)"
        assert len(sm.list_versions("perf-skill", workspace)) == 50

    def test_skill_load_current_under_100ms(self, workspace: Path) -> None:
        """Loading the current version of a skill should be under 100 ms."""
        sm.save_skill(
            name="fast-skill",
            description="Fast skill",
            inputs=[{"name": "x", "type": "string", "required": True}],
            outputs=[{"name": "y", "type": "string"}],
            base=workspace,
        )
        start = time.monotonic()
        for _ in range(50):
            sm.load_skill("fast-skill", base=workspace)
        elapsed = time.monotonic() - start
        avg_ms = (elapsed / 50) * 1000
        assert avg_ms < 100, f"Average skill load took {avg_ms:.1f}ms (expected < 100ms)"

    def test_tail_logs_1000_records_under_200ms(self, workspace: Path) -> None:
        """tail_logs(n=10) over 1000 records should be under 200 ms."""
        for i in range(1000):
            cl.log_call(
                skill=f"s{i}",
                model="gpt-4o",
                input_tokens=i,
                output_tokens=i // 2,
                duration=0.1,
                base=workspace,
            )
        start = time.monotonic()
        records = cl.tail_logs(n=10, base=workspace)
        elapsed = time.monotonic() - start
        assert elapsed < 0.2, f"tail_logs over 1000 records took {elapsed:.3f}s"
        assert len(records) == 10
        assert records[-1]["skill"] == "s999"

    def test_search_logs_under_500ms(self, workspace: Path) -> None:
        """search_logs(skill=...) over 500 records should be under 500 ms."""
        for i in range(500):
            cl.log_call(
                skill="target" if i % 5 == 0 else "other",
                model="gpt-4o",
                input_tokens=i,
                output_tokens=i // 2,
                duration=0.1,
                base=workspace,
            )
        start = time.monotonic()
        # Use a high limit so we get all matching records (100 total)
        results = cl.search_logs(skill="target", limit=200, base=workspace)
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"search_logs over 500 records took {elapsed:.3f}s"
        assert len(results) == 100  # every 5th record (0, 5, 10, ... 495)


# ---------------------------------------------------------------------------
# Test: multi-asset skill render
# ---------------------------------------------------------------------------


class TestSkillRender:

    def test_render_skill_prompt_contains_all_parts(
        self, full_workspace: Path
    ) -> None:
        """render_skill_prompt resolves system, user, rules, context."""
        rendered = sm.render_skill_prompt("code-reviewer", base=full_workspace)
        assert "senior" in rendered["system"]
        assert "review" in rendered["user"].lower()
        assert "no-speculation" in rendered["rules"]
        assert "output-json" in rendered["rules"]
        assert rendered["context"] != ""  # context template present

    def test_build_messages_contains_soft_rule(self, full_workspace: Path) -> None:
        """Assembling messages injects soft rules into system prompt."""
        from harness_kit.llm import build_messages

        rendered = sm.render_skill_prompt("code-reviewer", base=full_workspace)
        skill_data = sm.load_skill("code-reviewer", base=full_workspace)
        msgs = build_messages(skill_data, rendered, vars={"code": "x=1", "language": "python"})

        system_msgs = [m for m in msgs if m["role"] == "system"]
        assert len(system_msgs) > 0
        system_content = system_msgs[0]["content"]
        # Soft rule 'output-json' should be injected
        assert "output-json" in system_content or "JSON" in system_content

    def test_build_messages_hard_rule_not_in_system(
        self, full_workspace: Path
    ) -> None:
        """Hard rules are NOT injected into the system prompt."""
        from harness_kit.llm import build_messages

        rendered = sm.render_skill_prompt("code-reviewer", base=full_workspace)
        skill_data = sm.load_skill("code-reviewer", base=full_workspace)
        msgs = build_messages(skill_data, rendered, vars={"code": "x=1", "language": "python"})

        system_msgs = [m for m in msgs if m["role"] == "system"]
        assert len(system_msgs) > 0
        system_content = system_msgs[0]["content"]
        # Hard rule should NOT appear directly in system prompt
        assert "no-speculation" not in system_content
