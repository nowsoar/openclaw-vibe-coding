"""Tests for Phase 6.1: 调用日志系统 — call log system."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness_kit import call_logger as cl
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


def _write_record(base: Path, **kwargs) -> None:
    """Write a single log record directly to calls.jsonl."""
    log_file = base / ".harness" / "logs" / "calls.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "type": "llm_call",
        "skill": "test-skill",
        "model": "gpt-4o",
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
        "cost": 0.005,
        "duration": 1.0,
        "status": "success",
    }
    record.update(kwargs)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# Unit tests: call_logger module
# ---------------------------------------------------------------------------


class TestLogCall:
    def test_log_call_creates_file(self, workspace: Path) -> None:
        cl.log_call(
            skill="my-skill",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            duration=1.5,
            base=workspace,
        )
        log_file = workspace / ".harness" / "logs" / "calls.jsonl"
        assert log_file.exists()

    def test_log_call_fields(self, workspace: Path) -> None:
        cl.log_call(
            skill="my-skill",
            model="gpt-4o",
            input_tokens=200,
            output_tokens=80,
            duration=2.3,
            cost=0.012,
            status="success",
            base=workspace,
        )
        log_file = workspace / ".harness" / "logs" / "calls.jsonl"
        record = json.loads(log_file.read_text())
        assert record["type"] == "llm_call"
        assert record["skill"] == "my-skill"
        assert record["model"] == "gpt-4o"
        assert record["input_tokens"] == 200
        assert record["output_tokens"] == 80
        assert record["total_tokens"] == 280
        assert record["cost"] == 0.012
        assert record["duration"] == 2.3
        assert record["status"] == "success"
        assert "timestamp" in record

    def test_log_call_cost_field_optional(self, workspace: Path) -> None:
        """cost=None is allowed and stored as null."""
        cl.log_call(
            skill="s",
            model="m",
            input_tokens=10,
            output_tokens=5,
            duration=0.5,
            cost=None,
            base=workspace,
        )
        log_file = workspace / ".harness" / "logs" / "calls.jsonl"
        record = json.loads(log_file.read_text())
        assert record["cost"] is None

    def test_log_call_with_violations(self, workspace: Path) -> None:
        violations = [{"rule": "no-spam", "type": "hard", "matches": ["spam"], "fix_hint": "remove spam"}]
        cl.log_call(
            skill="s",
            model="m",
            input_tokens=10,
            output_tokens=5,
            duration=0.1,
            violations=violations,
            base=workspace,
        )
        record = json.loads((workspace / ".harness" / "logs" / "calls.jsonl").read_text())
        assert record["violation_count"] == 1
        assert record["violations"][0]["rule"] == "no-spam"

    def test_log_call_appends_multiple(self, workspace: Path) -> None:
        for i in range(3):
            cl.log_call(
                skill=f"skill-{i}",
                model="m",
                input_tokens=10,
                output_tokens=5,
                duration=0.1,
                base=workspace,
            )
        lines = (workspace / ".harness" / "logs" / "calls.jsonl").read_text().splitlines()
        assert len(lines) == 3


class TestTailLogs:
    def test_tail_empty(self, workspace: Path) -> None:
        assert cl.tail_logs(base=workspace) == []

    def test_tail_returns_last_n(self, workspace: Path) -> None:
        for i in range(10):
            _write_record(workspace, skill=f"skill-{i}")
        records = cl.tail_logs(n=5, base=workspace)
        assert len(records) == 5
        # Last record should be skill-9
        assert records[-1]["skill"] == "skill-9"

    def test_tail_since_filters_old(self, workspace: Path) -> None:
        """Records older than the since window are excluded."""
        log_file = workspace / ".harness" / "logs" / "calls.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # Old record: 2 days ago
        old_ts = (datetime.now(tz=timezone.utc) - timedelta(days=2)).isoformat()
        recent_ts = datetime.now(tz=timezone.utc).isoformat()
        for ts, skill in [(old_ts, "old-skill"), (recent_ts, "new-skill")]:
            record = {
                "timestamp": ts,
                "type": "llm_call",
                "skill": skill,
                "model": "m",
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "cost": 0.0,
                "duration": 0.1,
                "status": "success",
            }
            with log_file.open("a") as f:
                f.write(json.dumps(record) + "\n")

        records = cl.tail_logs(since="1d", base=workspace)
        skills = [r["skill"] for r in records]
        assert "new-skill" in skills
        assert "old-skill" not in skills


class TestSearchLogs:
    def test_search_by_skill(self, workspace: Path) -> None:
        _write_record(workspace, skill="reviewer")
        _write_record(workspace, skill="summarizer")
        _write_record(workspace, skill="reviewer")
        results = cl.search_logs(skill="reviewer", base=workspace)
        assert len(results) == 2
        assert all(r["skill"] == "reviewer" for r in results)

    def test_search_by_status(self, workspace: Path) -> None:
        _write_record(workspace, status="success")
        _write_record(workspace, status="error")
        _write_record(workspace, status="success")
        results = cl.search_logs(status="error", base=workspace)
        assert len(results) == 1
        assert results[0]["status"] == "error"

    def test_search_since_1d(self, workspace: Path) -> None:
        log_file = workspace / ".harness" / "logs" / "calls.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        old_ts = (datetime.now(tz=timezone.utc) - timedelta(days=3)).isoformat()
        recent_ts = datetime.now(tz=timezone.utc).isoformat()
        for ts, skill in [(old_ts, "old"), (recent_ts, "recent")]:
            record = {
                "timestamp": ts,
                "type": "llm_call",
                "skill": skill,
                "model": "m",
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "cost": 0.0,
                "duration": 0.1,
                "status": "success",
            }
            with log_file.open("a") as f:
                f.write(json.dumps(record) + "\n")
        results = cl.search_logs(since="1d", base=workspace)
        assert len(results) == 1
        assert results[0]["skill"] == "recent"

    def test_search_limit(self, workspace: Path) -> None:
        for i in range(20):
            _write_record(workspace, skill="s")
        results = cl.search_logs(limit=5, base=workspace)
        assert len(results) == 5

    def test_search_no_results(self, workspace: Path) -> None:
        assert cl.search_logs(skill="ghost", base=workspace) == []


class TestParseSince:
    def test_days(self) -> None:
        cutoff = cl._parse_since("1d")
        assert cutoff is not None
        delta = datetime.now(tz=timezone.utc) - cutoff
        assert 23 * 3600 < delta.total_seconds() < 25 * 3600

    def test_hours(self) -> None:
        cutoff = cl._parse_since("2h")
        assert cutoff is not None
        delta = datetime.now(tz=timezone.utc) - cutoff
        assert 1.9 * 3600 < delta.total_seconds() < 2.1 * 3600

    def test_minutes(self) -> None:
        cutoff = cl._parse_since("30m")
        assert cutoff is not None
        delta = datetime.now(tz=timezone.utc) - cutoff
        assert 29 * 60 < delta.total_seconds() < 31 * 60

    def test_none_returns_none(self) -> None:
        assert cl._parse_since(None) is None

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid --since"):
            cl._parse_since("5x")


class TestExportLogs:
    def test_export_csv_basic(self, workspace: Path) -> None:
        _write_record(workspace, skill="reviewer", model="gpt-4o", cost=0.01)
        data = cl.export_logs(fmt="csv", base=workspace)
        assert data
        reader = csv.DictReader(io.StringIO(data))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["skill"] == "reviewer"
        assert rows[0]["model"] == "gpt-4o"

    def test_export_csv_has_cost_field(self, workspace: Path) -> None:
        _write_record(workspace, cost=0.005)
        data = cl.export_logs(fmt="csv", base=workspace)
        reader = csv.DictReader(io.StringIO(data))
        rows = list(reader)
        assert "cost" in rows[0]

    def test_export_jsonl(self, workspace: Path) -> None:
        _write_record(workspace, skill="s1")
        _write_record(workspace, skill="s2")
        data = cl.export_logs(fmt="jsonl", base=workspace)
        lines = [l for l in data.splitlines() if l.strip()]
        assert len(lines) == 2
        assert json.loads(lines[0])["skill"] == "s1"

    def test_export_since_filter(self, workspace: Path) -> None:
        log_file = workspace / ".harness" / "logs" / "calls.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        old_ts = (datetime.now(tz=timezone.utc) - timedelta(days=10)).isoformat()
        recent_ts = datetime.now(tz=timezone.utc).isoformat()
        for ts, skill in [(old_ts, "old"), (recent_ts, "recent")]:
            rec = {
                "timestamp": ts, "type": "llm_call", "skill": skill,
                "model": "m", "input_tokens": 10, "output_tokens": 5,
                "total_tokens": 15, "cost": 0.0, "duration": 0.1, "status": "success",
            }
            with log_file.open("a") as f:
                f.write(json.dumps(rec) + "\n")
        data = cl.export_logs(fmt="csv", since="7d", base=workspace)
        reader = csv.DictReader(io.StringIO(data))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["skill"] == "recent"

    def test_export_empty(self, workspace: Path) -> None:
        assert cl.export_logs(base=workspace) == ""


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestCLILogsTail:
    def test_tail_empty(self, workspace: Path) -> None:
        result = runner.invoke(app, ["logs", "tail"])
        assert result.exit_code == 0
        assert "No call logs" in result.output

    def test_tail_shows_records(self, workspace: Path) -> None:
        _write_record(workspace, skill="my-skill", model="gpt-4o", cost=0.01)
        result = runner.invoke(app, ["logs", "tail"])
        assert result.exit_code == 0
        # Rich may truncate long strings in narrow terminals; check prefix
        assert "my-ski" in result.output
        assert "gpt-4o" in result.output

    def test_tail_since_option(self, workspace: Path) -> None:
        result = runner.invoke(app, ["logs", "tail", "--since", "1d"])
        assert result.exit_code == 0


class TestCLILogsSearch:
    def test_search_no_results(self, workspace: Path) -> None:
        result = runner.invoke(app, ["logs", "search", "--skill", "ghost"])
        assert result.exit_code == 0
        assert "No matching" in result.output

    def test_search_with_skill(self, workspace: Path) -> None:
        _write_record(workspace, skill="reviewer")
        _write_record(workspace, skill="other")
        result = runner.invoke(app, ["logs", "search", "--skill", "reviewer"])
        assert result.exit_code == 0
        # Rich may truncate; check prefix
        assert "review" in result.output

    def test_search_with_since(self, workspace: Path) -> None:
        _write_record(workspace, skill="reviewer")
        result = runner.invoke(app, ["logs", "search", "--since", "1d"])
        assert result.exit_code == 0
        # Rich may truncate long strings; check prefix
        assert "review" in result.output

    def test_search_since_excludes_old(self, workspace: Path) -> None:
        log_file = workspace / ".harness" / "logs" / "calls.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        old_ts = (datetime.now(tz=timezone.utc) - timedelta(days=5)).isoformat()
        rec = {
            "timestamp": old_ts, "type": "llm_call", "skill": "ancient",
            "model": "m", "input_tokens": 10, "output_tokens": 5,
            "total_tokens": 15, "cost": 0.0, "duration": 0.1, "status": "success",
        }
        with log_file.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        result = runner.invoke(app, ["logs", "search", "--since", "1d"])
        assert result.exit_code == 0
        assert "ancient" not in result.output


class TestCLILogsExport:
    def test_export_csv_stdout(self, workspace: Path) -> None:
        _write_record(workspace, skill="reviewer", cost=0.005)
        result = runner.invoke(app, ["logs", "export", "--format", "csv"])
        assert result.exit_code == 0
        assert "skill" in result.output  # CSV header
        assert "reviewer" in result.output

    def test_export_jsonl_stdout(self, workspace: Path) -> None:
        _write_record(workspace, skill="reviewer")
        result = runner.invoke(app, ["logs", "export", "--format", "jsonl"])
        assert result.exit_code == 0
        # Output should be valid JSON
        data = json.loads(result.output.strip().splitlines()[0])
        assert data["skill"] == "reviewer"

    def test_export_to_file(self, workspace: Path, tmp_path: Path) -> None:
        _write_record(workspace, skill="reviewer")
        out_file = tmp_path / "logs.csv"
        result = runner.invoke(app, ["logs", "export", "--format", "csv", "--output", str(out_file)])
        assert result.exit_code == 0
        assert out_file.exists()
        content = out_file.read_text()
        assert "reviewer" in content

    def test_export_since_filter(self, workspace: Path) -> None:
        _write_record(workspace, skill="reviewer")
        result = runner.invoke(app, ["logs", "export", "--format", "csv", "--since", "7d"])
        assert result.exit_code == 0
        assert "reviewer" in result.output

    def test_export_empty(self, workspace: Path) -> None:
        result = runner.invoke(app, ["logs", "export", "--format", "csv"])
        assert result.exit_code == 0
        assert "No call logs" in result.output

    def test_export_invalid_format(self, workspace: Path) -> None:
        result = runner.invoke(app, ["logs", "export", "--format", "xml"])
        assert result.exit_code != 0
