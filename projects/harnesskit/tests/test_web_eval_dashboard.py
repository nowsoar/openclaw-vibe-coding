"""Tests for Phase 8.5: Eval Dashboard (Web UI + API)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient

from harness_kit.config import init_harness
from harness_kit.eval import save_suite
from harness_kit.web import _STATIC_DIR, create_app

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SUITE_A: dict = {
    "name": "basic-suite",
    "description": "Basic test suite for unit tests",
    "cases": [
        {
            "id": "case-1",
            "name": "Check contains",
            "inputs": {"text": "hello world"},
            "assertions": [{"type": "contains", "path": "$", "value": "hello"}],
        },
        {
            "id": "case-2",
            "name": "Regex check",
            "inputs": {"text": "foo bar"},
            "assertions": [{"type": "regex", "path": "$", "pattern": "foo"}],
        },
    ],
}

SUITE_B: dict = {
    "name": "second-suite",
    "description": "Another suite",
    "cases": [
        {
            "id": "only-case",
            "name": "Single case",
            "inputs": {},
            "assertions": [{"type": "contains", "path": "$", "value": "result"}],
        }
    ],
}

SKILL_DATA: dict = {
    "name": "my-skill",
    "version": "v0.0.1",
    "description": "Test skill",
    "trigger": "test",
    "inputs": [{"name": "text", "type": "string", "required": True}],
    "outputs": [{"name": "out", "type": "string"}],
    "assets": {},
    "examples": [],
    "changelog": "init",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_skill(workspace: Path, skill: dict) -> None:
    name = skill["name"]
    version = skill["version"]
    sdir = workspace / ".harness" / "skills" / name
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / f"{version}.yaml").write_text(yaml.dump(skill), encoding="utf-8")
    (sdir / "_current").write_text(version, encoding="utf-8")


def _write_result(workspace: Path, target: str, suite: str, passed: int, total: int) -> None:
    from datetime import datetime, timezone

    rdir = workspace / ".harness" / "evals" / "results"
    rdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    ts_safe = ts.replace(":", "-").replace("+", "-").replace(".", "-")[:23]
    report = {
        "timestamp": ts,
        "target": target,
        "suite": suite,
        "summary": {"total": total, "passed": passed, "failed": total - passed},
        "cases": [],
    }
    (rdir / f"{ts_safe}.json").write_text(json.dumps(report), encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


@pytest.fixture()
def workspace_with_data(workspace: Path) -> Path:
    save_suite(SUITE_A, base=workspace)
    save_suite(SUITE_B, base=workspace)
    _write_skill(workspace, SKILL_DATA)
    _write_result(workspace, "my-skill@v0.0.1", "basic-suite", 2, 2)
    _write_result(workspace, "my-skill@v0.0.1", "basic-suite", 1, 2)
    return workspace


@pytest.fixture()
def client(workspace_with_data: Path) -> TestClient:
    return TestClient(create_app(base=workspace_with_data))


@pytest.fixture()
def client_empty(workspace: Path) -> TestClient:
    return TestClient(create_app(base=workspace))


# ---------------------------------------------------------------------------
# Tests: GET /api/eval/suites
# ---------------------------------------------------------------------------


class TestListEvalSuites:
    def test_returns_list(self, client: TestClient) -> None:
        r = client.get("/api/eval/suites")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_suite_summary_fields(self, client: TestClient) -> None:
        r = client.get("/api/eval/suites")
        suites = {s["name"]: s for s in r.json()}
        assert "basic-suite" in suites
        s = suites["basic-suite"]
        assert s["case_count"] == 2
        assert s["assertion_count"] == 2
        assert "description" in s

    def test_empty_returns_empty_list(self, client_empty: TestClient) -> None:
        r = client_empty.get("/api/eval/suites")
        assert r.status_code == 200
        assert r.json() == []

    def test_json_content_type(self, client: TestClient) -> None:
        r = client.get("/api/eval/suites")
        assert "application/json" in r.headers["content-type"]


# ---------------------------------------------------------------------------
# Tests: GET /api/eval/suites/{name}
# ---------------------------------------------------------------------------


class TestGetEvalSuite:
    def test_returns_suite_detail(self, client: TestClient) -> None:
        r = client.get("/api/eval/suites/basic-suite")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "basic-suite"
        assert "cases" in data
        assert len(data["cases"]) == 2

    def test_not_found_returns_404(self, client: TestClient) -> None:
        r = client.get("/api/eval/suites/nonexistent")
        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()

    def test_second_suite_returns_correct_data(self, client: TestClient) -> None:
        r = client.get("/api/eval/suites/second-suite")
        assert r.status_code == 200
        assert r.json()["name"] == "second-suite"


# ---------------------------------------------------------------------------
# Tests: POST /api/eval/suites/{name}/run
# ---------------------------------------------------------------------------

_MOCK_LLM_RESP = MagicMock(
    content="hello world",
    model="gpt-test",
    input_tokens=10,
    output_tokens=5,
    duration=0.1,
)


class TestRunEvalSuite:
    def test_missing_suite_returns_404(self, client: TestClient) -> None:
        r = client.post("/api/eval/suites/no-suite/run", json={"target": "my-skill"})
        assert r.status_code == 404

    def test_missing_skill_returns_404(self, client: TestClient) -> None:
        r = client.post("/api/eval/suites/basic-suite/run", json={"target": "ghost-skill"})
        assert r.status_code == 404

    def test_no_api_key_returns_503(self, client: TestClient) -> None:
        with patch("harness_kit.llm.LLMConfig.from_harness_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(api_key=None)
            r = client.post("/api/eval/suites/basic-suite/run", json={"target": "my-skill"})
        assert r.status_code == 503

    def test_successful_run_returns_report(self, client: TestClient) -> None:
        with (
            patch("harness_kit.skill.render_skill_prompt", return_value={"system": "", "user": ""}),
            patch("harness_kit.llm.LLMConfig.from_harness_config") as mock_cfg,
            patch("harness_kit.llm.call_llm", return_value=_MOCK_LLM_RESP),
            patch("harness_kit.llm.build_messages", return_value=[]),
        ):
            mock_cfg.return_value = MagicMock(api_key="test-key")
            r = client.post("/api/eval/suites/basic-suite/run", json={"target": "my-skill"})

        assert r.status_code == 200
        report = r.json()
        assert "summary" in report
        assert "cases" in report
        assert report["suite"] == "basic-suite"
        assert report["summary"]["total"] == 2

    def test_report_persisted_to_results(self, workspace_with_data: Path) -> None:
        """Running suite creates a result JSON file."""
        client = TestClient(create_app(base=workspace_with_data))
        rdir = workspace_with_data / ".harness" / "evals" / "results"
        before = len(list(rdir.glob("*.json")))

        with (
            patch("harness_kit.skill.render_skill_prompt", return_value={"system": "", "user": ""}),
            patch("harness_kit.llm.LLMConfig.from_harness_config") as mock_cfg,
            patch("harness_kit.llm.call_llm", return_value=_MOCK_LLM_RESP),
            patch("harness_kit.llm.build_messages", return_value=[]),
        ):
            mock_cfg.return_value = MagicMock(api_key="test-key")
            r = client.post("/api/eval/suites/basic-suite/run", json={"target": "my-skill"})

        assert r.status_code == 200
        after = len(list(rdir.glob("*.json")))
        assert after == before + 1


# ---------------------------------------------------------------------------
# Tests: GET /api/eval/results
# ---------------------------------------------------------------------------


class TestListEvalResults:
    def test_returns_list(self, client: TestClient) -> None:
        r = client.get("/api/eval/results")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_has_expected_fields(self, client: TestClient) -> None:
        r = client.get("/api/eval/results")
        results = r.json()
        assert len(results) >= 1
        first = results[0]
        assert "timestamp" in first
        assert "target" in first
        assert "suite" in first
        assert "summary" in first

    def test_summary_fields(self, client: TestClient) -> None:
        r = client.get("/api/eval/results")
        for res in r.json():
            s = res["summary"]
            assert "total" in s
            assert "passed" in s
            assert "failed" in s

    def test_empty_returns_empty_list(self, client_empty: TestClient) -> None:
        r = client_empty.get("/api/eval/results")
        assert r.status_code == 200
        assert r.json() == []

    def test_limit_param(self, workspace_with_data: Path) -> None:
        # Write more results
        for i in range(5):
            _write_result(workspace_with_data, f"skill-{i}", "basic-suite", 1, 1)
        c = TestClient(create_app(base=workspace_with_data))
        r = c.get("/api/eval/results?limit=3")
        assert r.status_code == 200
        assert len(r.json()) <= 3

    def test_ordered_newest_first(self, client: TestClient) -> None:
        r = client.get("/api/eval/results")
        results = r.json()
        if len(results) >= 2:
            # Timestamps should be descending (newest first)
            ts0 = results[0]["timestamp"]
            ts1 = results[1]["timestamp"]
            assert ts0 >= ts1


# ---------------------------------------------------------------------------
# Tests: GET /api/eval/trend
# ---------------------------------------------------------------------------


class TestGetEvalTrend:
    def test_returns_list(self, client: TestClient) -> None:
        r = client.get("/api/eval/trend")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_trend_fields(self, client: TestClient) -> None:
        r = client.get("/api/eval/trend")
        for pt in r.json():
            assert "timestamp" in pt
            assert "target" in pt
            assert "suite" in pt
            assert "pass_rate" in pt
            assert "passed" in pt
            assert "total" in pt

    def test_pass_rate_range(self, client: TestClient) -> None:
        r = client.get("/api/eval/trend")
        for pt in r.json():
            assert 0.0 <= pt["pass_rate"] <= 1.0

    def test_empty_returns_empty_list(self, client_empty: TestClient) -> None:
        r = client_empty.get("/api/eval/trend")
        assert r.status_code == 200
        assert r.json() == []

    def test_target_filter(self, client: TestClient) -> None:
        r = client.get("/api/eval/trend?target=my-skill")
        assert r.status_code == 200
        for pt in r.json():
            assert "my-skill" in pt["target"].lower()

    def test_suite_filter(self, client: TestClient) -> None:
        r = client.get("/api/eval/trend?suite=basic-suite")
        assert r.status_code == 200
        for pt in r.json():
            assert pt["suite"] == "basic-suite"

    def test_limit_param(self, workspace_with_data: Path) -> None:
        for i in range(10):
            _write_result(workspace_with_data, f"skill-{i}", "basic-suite", 1, 1)
        c = TestClient(create_app(base=workspace_with_data))
        r = c.get("/api/eval/trend?limit=5")
        assert r.status_code == 200
        assert len(r.json()) <= 5


# ---------------------------------------------------------------------------
# Tests: eval.html partial structure
# ---------------------------------------------------------------------------


class TestEvalPartialExists:
    def test_partial_file_exists(self) -> None:
        partial = _STATIC_DIR / "partials" / "eval.html"
        assert partial.exists(), "eval.html partial must exist"

    def test_partial_served_via_api(self, client: TestClient) -> None:
        r = client.get("/partials/eval")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]


class TestEvalPartialStructure:
    """Verify that eval.html contains required IDs and Alpine.js bindings."""

    @pytest.fixture(autouse=True)
    def html(self) -> str:
        return (_STATIC_DIR / "partials" / "eval.html").read_text(encoding="utf-8")

    def test_has_alpine_component(self, html: str) -> None:
        assert "x-data" in html
        assert "evalSection" in html

    def test_has_stats_ids(self, html: str) -> None:
        assert 'id="eval-stats-suites"' in html
        assert 'id="eval-stats-passed"' in html
        assert 'id="eval-stats-failed"' in html

    def test_has_suite_list_id(self, html: str) -> None:
        assert 'id="eval-suite-list"' in html

    def test_has_suite_search_id(self, html: str) -> None:
        assert 'id="eval-suite-search"' in html

    def test_has_results_table_id(self, html: str) -> None:
        assert 'id="eval-results-table"' in html

    def test_has_trend_chart_id(self, html: str) -> None:
        assert 'id="eval-trend-chart"' in html

    def test_has_run_button_id(self, html: str) -> None:
        assert 'id="eval-run-btn"' in html

    def test_has_run_target_id(self, html: str) -> None:
        assert 'id="eval-run-target"' in html

    def test_has_run_error_id(self, html: str) -> None:
        assert 'id="eval-run-error"' in html

    def test_has_svg_sparkline(self, html: str) -> None:
        assert "<svg" in html
        assert "<polyline" in html

    def test_has_x_init_load(self, html: str) -> None:
        assert "x-init" in html
        assert "load()" in html

    def test_has_api_calls(self, html: str) -> None:
        assert "/api/eval/suites" in html
        assert "/api/eval/results" in html
        assert "/api/eval/trend" in html

    def test_has_run_method_call(self, html: str) -> None:
        assert "/run" in html

    def test_has_empty_state(self, html: str) -> None:
        # At least one empty-state element
        assert "eval-suite-empty" in html or "eval-results-empty" in html

    def test_has_trend_legend(self, html: str) -> None:
        # Trend legend with color indicators
        assert "100%" in html
        assert "70%" in html


# ---------------------------------------------------------------------------
# Tests: Backwards compatibility with Phases 8.1–8.4
# ---------------------------------------------------------------------------


class TestBackwardsCompatibility:
    def test_skills_api_still_works(self, client: TestClient) -> None:
        r = client.get("/api/skills")
        assert r.status_code == 200

    def test_skill_detail_still_works(self, client: TestClient) -> None:
        r = client.get("/api/skills/my-skill")
        assert r.status_code == 200

    def test_skill_versions_still_works(self, client: TestClient) -> None:
        r = client.get("/api/skills/my-skill/versions")
        assert r.status_code == 200

    def test_compare_endpoint_still_registered(self, client: TestClient) -> None:
        # POST /api/compare with missing skill → 404 (endpoint exists)
        r = client.post("/api/compare", json={
            "skill": "ghost", "version_a": "v0.0.1", "version_b": "v0.0.2",
            "inputs": {}, "model": None,
        })
        assert r.status_code in (404, 503)

    def test_partial_skills_still_works(self, client: TestClient) -> None:
        r = client.get("/partials/skills")
        assert r.status_code == 200

    def test_partial_compare_still_works(self, client: TestClient) -> None:
        r = client.get("/partials/compare")
        assert r.status_code == 200

    def test_index_still_works(self, client: TestClient) -> None:
        r = client.get("/")
        assert r.status_code == 200
