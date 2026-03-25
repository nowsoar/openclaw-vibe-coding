"""Phase 6.6 integration test — complete observability pipeline.

Covers the end-to-end flow:
  init → write call logs → tail / search / export logs →
  cost report → stats dashboard → improvement log →
  health check → health fix

Also includes performance regression tests for the streaming log reader.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness_kit import call_logger as cl
from harness_kit import cost_tracker as ct
from harness_kit import improvement as imp
from harness_kit import stats as st
from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit.health import run_health_check

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ws(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Initialised HarnessKit workspace in a temp dir."""
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


def _write_log(
    base: Path,
    *,
    skill: str = "test-skill",
    model: str = "gpt-4o",
    input_tokens: int = 200,
    output_tokens: int = 80,
    cost: float = 0.005,
    duration: float = 1.2,
    status: str = "success",
    ts_offset_days: int = 0,
    violations: list | None = None,
) -> None:
    """Write a call-log record with an optional timestamp offset (negative = past)."""
    log_file = base / ".harness" / "logs" / "calls.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    ts = (datetime.now(tz=timezone.utc) - timedelta(days=abs(ts_offset_days))).isoformat()
    record: dict = {
        "timestamp": ts,
        "type": "llm_call",
        "skill": skill,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost": cost,
        "duration": duration,
        "status": status,
    }
    if violations:
        record["violations"] = violations
        record["violation_count"] = len(violations)
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# 1. Log write → read pipeline
# ---------------------------------------------------------------------------


class TestLogPipeline:
    def test_write_and_tail(self, ws: Path) -> None:
        for i in range(5):
            cl.log_call(
                skill=f"skill-{i}",
                model="gpt-4o",
                input_tokens=100 * (i + 1),
                output_tokens=50,
                duration=float(i + 1),
                cost=0.001 * (i + 1),
                base=ws,
            )
        records = cl.tail_logs(base=ws)
        assert len(records) == 5
        # Last written is last in the list
        assert records[-1]["skill"] == "skill-4"

    def test_search_by_skill_filters_correctly(self, ws: Path) -> None:
        _write_log(ws, skill="reviewer")
        _write_log(ws, skill="summarizer")
        _write_log(ws, skill="reviewer")

        found = cl.search_logs(skill="reviewer", base=ws)
        assert len(found) == 2
        assert all(r["skill"] == "reviewer" for r in found)

    def test_search_since_excludes_old_records(self, ws: Path) -> None:
        _write_log(ws, skill="old-skill", ts_offset_days=5)
        _write_log(ws, skill="new-skill", ts_offset_days=0)

        recent = cl.search_logs(since="1d", base=ws)
        skills = {r["skill"] for r in recent}
        assert "new-skill" in skills
        assert "old-skill" not in skills

    def test_export_csv_contains_all_fields(self, ws: Path) -> None:
        _write_log(ws, skill="my-skill", cost=0.01)
        csv_data = cl.export_logs(fmt="csv", base=ws)
        assert "my-skill" in csv_data
        assert "cost" in csv_data
        assert "0.01" in csv_data

    def test_export_jsonl_roundtrip(self, ws: Path) -> None:
        _write_log(ws, skill="s1")
        _write_log(ws, skill="s2")
        jsonl = cl.export_logs(fmt="jsonl", base=ws)
        lines = [l for l in jsonl.splitlines() if l.strip()]
        assert len(lines) == 2
        assert json.loads(lines[0])["skill"] == "s1"
        assert json.loads(lines[1])["skill"] == "s2"

    def test_violation_stats_aggregates_counts(self, ws: Path) -> None:
        violations = [{"rule": "no-spam", "type": "hard", "matches": [], "fix_hint": ""}]
        cl.log_call(
            skill="s",
            model="m",
            input_tokens=10,
            output_tokens=5,
            duration=0.1,
            violations=violations,
            base=ws,
        )
        cl.log_call(
            skill="s",
            model="m",
            input_tokens=10,
            output_tokens=5,
            duration=0.1,
            violations=violations,
            base=ws,
        )
        stats = cl.violation_stats(base=ws)
        assert stats.get("no-spam") == 2


# ---------------------------------------------------------------------------
# 2. Cost tracking pipeline
# ---------------------------------------------------------------------------


class TestCostPipeline:
    def test_estimate_cost_known_model(self, ws: Path) -> None:
        cost = ct.estimate_cost(model="gpt-4o", input_tokens=1000, output_tokens=500)
        # gpt-4o: $0.0025/1K in + $0.010/1K out
        expected = (1000 / 1000) * 0.0025 + (500 / 1000) * 0.010
        assert abs(cost - expected) < 1e-9

    def test_cost_report_aggregates_skills(self, ws: Path) -> None:
        for _ in range(3):
            _write_log(ws, skill="skill-a", cost=0.01)
        for _ in range(2):
            _write_log(ws, skill="skill-b", cost=0.05)

        report = ct.cost_report(since="7d", base=ws)
        # by_skill is a dict keyed by skill name
        assert "skill-a" in report["by_skill"]
        assert "skill-b" in report["by_skill"]

        total = report["total_cost"]
        assert abs(total - (3 * 0.01 + 2 * 0.05)) < 1e-6

    def test_cost_report_cli_runs(self, ws: Path) -> None:
        _write_log(ws, skill="cli-skill", cost=0.007)
        result = runner.invoke(app, ["cost", "report"])
        assert result.exit_code == 0
        assert "cli-skill" in result.output or "0.007" in result.output

    def test_cost_breakdown_by_model(self, ws: Path) -> None:
        _write_log(ws, skill="s", model="gpt-4o", cost=0.01)
        _write_log(ws, skill="s", model="gpt-4o-mini", cost=0.002)
        report = ct.cost_report(since="7d", base=ws)
        # by_model is a dict keyed by model name
        assert "gpt-4o" in report["by_model"]
        assert "gpt-4o-mini" in report["by_model"]


# ---------------------------------------------------------------------------
# 3. Stats dashboard pipeline
# ---------------------------------------------------------------------------


class TestStatsPipeline:
    def test_skill_stats_success_rate(self, ws: Path) -> None:
        for _ in range(8):
            _write_log(ws, skill="reviewer", status="success")
        for _ in range(2):
            _write_log(ws, skill="reviewer", status="error")

        data = st.skill_stats("reviewer", since=None, base=ws)
        assert data["total_calls"] == 10
        assert abs(data["success_rate"] - 0.8) < 0.001

    def test_skill_stats_duration_buckets(self, ws: Path) -> None:
        _write_log(ws, skill="s", duration=0.5)
        _write_log(ws, skill="s", duration=2.0)
        _write_log(ws, skill="s", duration=8.0)
        data = st.skill_stats("s", since=None, base=ws)
        assert data["total_calls"] == 3
        assert sum(data["duration_buckets"].values()) == 3

    def test_stats_cli_runs(self, ws: Path) -> None:
        _write_log(ws, skill="cli-skill")
        result = runner.invoke(app, ["stats", "show", "cli-skill"])
        assert result.exit_code == 0
        assert "cli-skill" in result.output or "1" in result.output

    def test_stats_token_distribution(self, ws: Path) -> None:
        _write_log(ws, skill="s", input_tokens=50, output_tokens=30)   # total=80
        _write_log(ws, skill="s", input_tokens=200, output_tokens=100)  # total=300
        data = st.skill_stats("s", since=None, base=ws)
        assert data["total_calls"] == 2
        assert sum(data["token_buckets"].values()) == 2


# ---------------------------------------------------------------------------
# 4. Improvement flywheel pipeline
# ---------------------------------------------------------------------------


class TestImprovementPipeline:
    def test_log_and_retrieve_improvement(self, ws: Path) -> None:
        imp.log_improvement(
            skill="code-reviewer",
            issue="输出不存在的函数",
            root_cause="缺少 hallucination 检查",
            fix="添加 no-hallucination rule",
            before_version="v0.1.0",
            after_version="v0.1.1",
            eval_improvement="+12%",
            base=ws,
        )
        history = imp.get_history("code-reviewer", base=ws)
        assert len(history) == 1
        record = history[0]
        assert record["issue"] == "输出不存在的函数"
        assert record["fix"] == "添加 no-hallucination rule"
        assert record["eval_improvement"] == "+12%"

    def test_multiple_improvements_stored(self, ws: Path) -> None:
        for i in range(3):
            imp.log_improvement(
                skill="summarizer",
                issue=f"issue-{i}",
                root_cause="root",
                fix=f"fix-{i}",
                before_version="v0.1.0",
                after_version=f"v0.1.{i + 1}",
                base=ws,
            )
        history = imp.get_history("summarizer", base=ws)
        assert len(history) == 3

    def test_improvement_report_period_week(self, ws: Path) -> None:
        imp.log_improvement(
            skill="s",
            issue="bug",
            root_cause="cause",
            fix="solution",
            before_version="v0.0.1",
            after_version="v0.0.2",
            base=ws,
        )
        report = imp.improvement_report(period="week", base=ws)
        assert report["total"] == 1
        assert "s" in report["by_skill"]

    def test_improve_history_cli(self, ws: Path) -> None:
        imp.log_improvement(
            skill="my-skill",
            issue="hallucination",
            root_cause="prompt",
            fix="add rule",
            before_version="v0.1.0",
            after_version="v0.1.1",
            base=ws,
        )
        result = runner.invoke(app, ["improve", "history", "my-skill"])
        assert result.exit_code == 0
        assert "hallucination" in result.output or "my-skill" in result.output


# ---------------------------------------------------------------------------
# 5. Health check pipeline
# ---------------------------------------------------------------------------


class TestHealthPipeline:
    def test_clean_workspace_no_issues(self, ws: Path) -> None:
        report = run_health_check(base=ws)
        assert len(report.issues) == 0
        assert len(report.critical_issues) == 0

    def test_detects_stale_skill(self, ws: Path) -> None:
        # Create a skill dir with a very old mtime
        skill_dir = ws / ".harness" / "skills" / "old-skill"
        skill_dir.mkdir(parents=True)
        old_v = skill_dir / "v0.0.1.yaml"
        old_v.write_text("name: old-skill\nversion: v0.0.1\n")
        # Set mtime to 20 days ago
        past = time.time() - 20 * 86400
        import os
        os.utime(old_v, (past, past))
        (skill_dir / "_current").write_text("v0.0.1")

        report = run_health_check(base=ws, stale_days=14)
        stale = [i for i in report.issues if i.category == "staleness"]
        assert len(stale) >= 1

    def test_detects_unused_asset(self, ws: Path) -> None:
        # Create an orphan prompt not referenced by any skill
        prompt_dir = ws / ".harness" / "prompts" / "orphan-prompt"
        prompt_dir.mkdir(parents=True)
        (prompt_dir / "v0.0.1.yaml").write_text("name: orphan-prompt\nversion: v0.0.1\ncontent: hi\n")
        (prompt_dir / "_current").write_text("v0.0.1")

        report = run_health_check(base=ws)
        unused = [i for i in report.issues if i.category == "unused_asset"]
        assert len(unused) >= 1

    def test_health_check_cli_runs(self, ws: Path) -> None:
        result = runner.invoke(app, ["health", "check"])
        assert result.exit_code == 0
        assert "Health Check" in result.output or "healthy" in result.output.lower()

    def test_health_fix_dry_run_no_changes(self, ws: Path) -> None:
        # Create orphan prompt
        prompt_dir = ws / ".harness" / "prompts" / "draft"
        prompt_dir.mkdir(parents=True)
        (prompt_dir / "v0.0.1.yaml").write_text("name: draft\nversion: v0.0.1\ncontent: hi\n")
        (prompt_dir / "_current").write_text("v0.0.1")

        result = runner.invoke(app, ["health", "fix", "--dry-run"])
        assert result.exit_code == 0
        # dry-run must NOT delete the directory
        assert prompt_dir.exists()


# ---------------------------------------------------------------------------
# 6. End-to-end observability flow
# ---------------------------------------------------------------------------


class TestEndToEndFlow:
    def test_full_observability_pipeline(self, ws: Path) -> None:
        """Complete flow: write logs → cost report → stats → improvement → health."""
        # Step 1: write a batch of logs for two skills
        for i in range(5):
            _write_log(ws, skill="code-reviewer", model="gpt-4o",
                       input_tokens=300, output_tokens=150, cost=0.0045, status="success")
        _write_log(ws, skill="code-reviewer", model="gpt-4o",
                   input_tokens=200, output_tokens=80, cost=0.003, status="error")
        for i in range(3):
            _write_log(ws, skill="summarizer", model="gpt-4o-mini",
                       input_tokens=100, output_tokens=50, cost=0.0001, status="success")

        # Step 2: verify tail returns all records
        all_logs = cl.tail_logs(n=100, base=ws)
        assert len(all_logs) == 9

        # Step 3: cost report covers both skills
        cost_rep = ct.cost_report(since="7d", base=ws)
        skill_names = set(cost_rep["by_skill"].keys())
        assert "code-reviewer" in skill_names
        assert "summarizer" in skill_names

        # Step 4: stats for code-reviewer show 5/6 success rate
        data = st.skill_stats("code-reviewer", since=None, base=ws)
        assert data["total_calls"] == 6
        assert abs(data["success_rate"] - (5 / 6)) < 0.01

        # Step 5: log an improvement
        imp.log_improvement(
            skill="code-reviewer",
            issue="occasionally hallucinated function names",
            root_cause="no hallucination rule",
            fix="added no-hallucination hard rule",
            before_version="v0.1.0",
            after_version="v0.1.1",
            eval_improvement="+8%",
            base=ws,
        )
        history = imp.get_history("code-reviewer", base=ws)
        assert len(history) == 1

        # Step 6: health check passes on a clean workspace (no skills in .harness/)
        report = run_health_check(base=ws)
        # No critical issues expected (error logs alone don't create health issues
        # unless success rate drops below threshold with ≥ 5 calls)
        assert len(report.critical_issues) == 0

    def test_cli_observability_workflow(self, ws: Path) -> None:
        """Verify CLI commands chain together for the observability workflow."""
        _write_log(ws, skill="review", model="gpt-4o", cost=0.01)

        # logs tail
        r = runner.invoke(app, ["logs", "tail"])
        assert r.exit_code == 0

        # logs search
        r = runner.invoke(app, ["logs", "search", "--skill", "review"])
        assert r.exit_code == 0

        # logs export
        r = runner.invoke(app, ["logs", "export", "--format", "csv"])
        assert r.exit_code == 0
        assert "review" in r.output

        # cost report
        r = runner.invoke(app, ["cost", "report"])
        assert r.exit_code == 0

        # stats show
        r = runner.invoke(app, ["stats", "show", "review"])
        assert r.exit_code == 0

        # health check
        r = runner.invoke(app, ["health", "check"])
        assert r.exit_code == 0


# ---------------------------------------------------------------------------
# 7. Performance regression tests
# ---------------------------------------------------------------------------


class TestPerformance:
    def test_tail_large_logfile_uses_deque(self, ws: Path) -> None:
        """Writing 1000 records and tailing the last 10 stays below 1 s."""
        for i in range(1000):
            _write_log(ws, skill=f"skill-{i % 10}", cost=0.001)

        start = time.monotonic()
        records = cl.tail_logs(n=10, base=ws)
        elapsed = time.monotonic() - start

        assert len(records) == 10
        assert elapsed < 1.0, f"tail_logs took {elapsed:.2f}s on 1000 records"

    def test_search_large_logfile_is_fast(self, ws: Path) -> None:
        """Searching 1000 records by skill completes in under 1 s."""
        for i in range(1000):
            skill = "target" if i % 100 == 0 else f"other-{i}"
            _write_log(ws, skill=skill, cost=0.001)

        start = time.monotonic()
        results = cl.search_logs(skill="target", base=ws)
        elapsed = time.monotonic() - start

        assert len(results) == 10  # i=0,100,200,...,900
        assert elapsed < 1.0, f"search_logs took {elapsed:.2f}s on 1000 records"

    def test_export_large_logfile_csv(self, ws: Path) -> None:
        """Exporting 500 records to CSV completes in under 1 s."""
        for i in range(500):
            _write_log(ws, skill=f"skill-{i % 5}", cost=0.001)

        start = time.monotonic()
        csv_data = cl.export_logs(fmt="csv", base=ws)
        elapsed = time.monotonic() - start

        lines = [l for l in csv_data.splitlines() if l.strip()]
        assert len(lines) == 501  # header + 500 records
        assert elapsed < 1.0, f"export_logs took {elapsed:.2f}s on 500 records"
