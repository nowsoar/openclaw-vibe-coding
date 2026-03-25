"""Tests for Phase 8.4: A/B Compare (Web UI + API)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient

from harness_kit.config import init_harness
from harness_kit.web import _STATIC_DIR, create_app

# ---------------------------------------------------------------------------
# Sample skill data
# ---------------------------------------------------------------------------

SKILL_V1: dict = {
    "name": "summarize",
    "version": "v0.0.1",
    "description": "Summarise text concisely",
    "trigger": "When a summary is needed",
    "inputs": [
        {"name": "text", "type": "string", "required": True},
        {"name": "style", "type": "string", "required": False, "default": "brief"},
    ],
    "outputs": [{"name": "summary", "type": "string"}],
    "assets": {},
    "examples": [],
    "changelog": "initial version",
}

SKILL_V2: dict = {
    **SKILL_V1,
    "version": "v0.0.2",
    "description": "Summarise text with optional bullet points",
    "changelog": "added bullet option",
}

SKILL_NO_INPUTS: dict = {
    "name": "ping",
    "version": "v0.0.1",
    "description": "Health check skill",
    "trigger": "ping",
    "inputs": [],
    "outputs": [{"name": "reply", "type": "string"}],
    "assets": {},
    "examples": [],
    "changelog": "initial",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_skill_version(workspace: Path, skill_data: dict) -> None:
    name = skill_data["name"]
    version = skill_data["version"]
    skill_dir = workspace / ".harness" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / f"{version}.yaml").write_text(yaml.dump(skill_data), encoding="utf-8")
    (skill_dir / "_current").write_text(version, encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


@pytest.fixture()
def workspace_multi(workspace: Path) -> Path:
    """Workspace with two versions of 'summarize' and one version of 'ping'."""
    _write_skill_version(workspace, SKILL_V1)
    _write_skill_version(workspace, SKILL_V2)  # overwrites _current → v0.0.2
    _write_skill_version(workspace, SKILL_NO_INPUTS)
    return workspace


@pytest.fixture()
def client(workspace_multi: Path) -> TestClient:
    return TestClient(create_app(base=workspace_multi))


@pytest.fixture()
def client_empty(workspace: Path) -> TestClient:
    return TestClient(create_app(base=workspace))


# ---------------------------------------------------------------------------
# Test: GET /api/skills/{name}/versions
# ---------------------------------------------------------------------------


class TestListSkillVersions:
    def test_returns_list_of_versions(self, client: TestClient) -> None:
        r = client.get("/api/skills/summarize/versions")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert "v0.0.1" in data
        assert "v0.0.2" in data

    def test_versions_sorted_oldest_first(self, client: TestClient) -> None:
        r = client.get("/api/skills/summarize/versions")
        assert r.status_code == 200
        versions = r.json()
        assert versions[0] == "v0.0.1"
        assert versions[-1] == "v0.0.2"

    def test_single_version_skill(self, client: TestClient) -> None:
        r = client.get("/api/skills/ping/versions")
        assert r.status_code == 200
        assert r.json() == ["v0.0.1"]

    def test_not_found_returns_404(self, client: TestClient) -> None:
        r = client.get("/api/skills/nonexistent/versions")
        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()

    def test_json_content_type(self, client: TestClient) -> None:
        r = client.get("/api/skills/summarize/versions")
        assert "application/json" in r.headers["content-type"]


# ---------------------------------------------------------------------------
# Test: POST /api/compare
# ---------------------------------------------------------------------------

_MOCK_RESP_A = MagicMock(
    content="Version A output",
    model="gpt-mock",
    input_tokens=10,
    output_tokens=5,
    duration=0.5,
)
_MOCK_RESP_B = MagicMock(
    content="Version B output with extra detail",
    model="gpt-mock",
    input_tokens=10,
    output_tokens=8,
    duration=0.6,
)


class TestCompareEndpoint:

    @patch("harness_kit.llm.call_llm")
    @patch("harness_kit.llm.LLMConfig.from_harness_config")
    def test_compare_success(
        self,
        mock_cfg: MagicMock,
        mock_llm: MagicMock,
        client: TestClient,
    ) -> None:
        mock_cfg.return_value = MagicMock(api_key="sk-test")
        mock_llm.side_effect = [_MOCK_RESP_A, _MOCK_RESP_B]

        r = client.post(
            "/api/compare",
            json={
                "skill": "summarize",
                "version_a": "v0.0.1",
                "version_b": "v0.0.2",
                "inputs": {"text": "Hello world", "style": "brief"},
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "result_a" in data
        assert "result_b" in data

    @patch("harness_kit.llm.call_llm")
    @patch("harness_kit.llm.LLMConfig.from_harness_config")
    def test_compare_response_shape(
        self,
        mock_cfg: MagicMock,
        mock_llm: MagicMock,
        client: TestClient,
    ) -> None:
        mock_cfg.return_value = MagicMock(api_key="sk-test")
        mock_llm.side_effect = [_MOCK_RESP_A, _MOCK_RESP_B]

        r = client.post(
            "/api/compare",
            json={
                "skill": "summarize",
                "version_a": "v0.0.1",
                "version_b": "v0.0.2",
                "inputs": {"text": "test"},
            },
        )
        assert r.status_code == 200
        data = r.json()
        for side in ("result_a", "result_b"):
            assert "output" in data[side]
            assert "model" in data[side]
            assert "input_tokens" in data[side]
            assert "output_tokens" in data[side]
            assert "duration" in data[side]
            assert "skill" in data[side]
            assert "version" in data[side]

    @patch("harness_kit.llm.call_llm")
    @patch("harness_kit.llm.LLMConfig.from_harness_config")
    def test_compare_carries_correct_versions(
        self,
        mock_cfg: MagicMock,
        mock_llm: MagicMock,
        client: TestClient,
    ) -> None:
        mock_cfg.return_value = MagicMock(api_key="sk-test")
        mock_llm.side_effect = [_MOCK_RESP_A, _MOCK_RESP_B]

        r = client.post(
            "/api/compare",
            json={
                "skill": "summarize",
                "version_a": "v0.0.1",
                "version_b": "v0.0.2",
                "inputs": {"text": "hello"},
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["result_a"]["version"] == "v0.0.1"
        assert data["result_b"]["version"] == "v0.0.2"

    def test_compare_skill_not_found_returns_404(self, client: TestClient) -> None:
        r = client.post(
            "/api/compare",
            json={
                "skill": "ghost",
                "version_a": "v0.0.1",
                "version_b": "v0.0.2",
                "inputs": {},
            },
        )
        assert r.status_code == 404

    def test_compare_version_not_found_returns_404(self, client: TestClient) -> None:
        r = client.post(
            "/api/compare",
            json={
                "skill": "summarize",
                "version_a": "v9.9.9",
                "version_b": "v0.0.2",
                "inputs": {"text": "hi"},
            },
        )
        assert r.status_code == 404

    def test_compare_missing_required_input_returns_422(
        self, client: TestClient
    ) -> None:
        r = client.post(
            "/api/compare",
            json={
                "skill": "summarize",
                "version_a": "v0.0.1",
                "version_b": "v0.0.2",
                "inputs": {},  # 'text' is required but missing
            },
        )
        assert r.status_code == 422

    def test_compare_no_api_key_returns_503(self, client: TestClient) -> None:
        with patch("harness_kit.config.read_config", return_value={}):
            with patch("harness_kit.llm.LLMConfig.from_harness_config") as mock_lc:
                mock_lc.return_value = MagicMock(api_key=None)
                r = client.post(
                    "/api/compare",
                    json={
                        "skill": "summarize",
                        "version_a": "v0.0.1",
                        "version_b": "v0.0.2",
                        "inputs": {"text": "hi"},
                    },
                )
        assert r.status_code == 503

    @patch("harness_kit.llm.call_llm")
    @patch("harness_kit.llm.LLMConfig.from_harness_config")
    def test_compare_model_override(
        self,
        mock_cfg: MagicMock,
        mock_llm: MagicMock,
        client: TestClient,
    ) -> None:
        mock_cfg.return_value = MagicMock(api_key="sk-test")
        mock_llm.side_effect = [_MOCK_RESP_A, _MOCK_RESP_B]

        r = client.post(
            "/api/compare",
            json={
                "skill": "summarize",
                "version_a": "v0.0.1",
                "version_b": "v0.0.2",
                "inputs": {"text": "test"},
                "model": "gpt-4o-mini",
            },
        )
        assert r.status_code == 200

    @patch("harness_kit.llm.call_llm")
    @patch("harness_kit.llm.LLMConfig.from_harness_config")
    def test_compare_same_version_both_sides(
        self,
        mock_cfg: MagicMock,
        mock_llm: MagicMock,
        client: TestClient,
    ) -> None:
        mock_cfg.return_value = MagicMock(api_key="sk-test")
        mock_llm.side_effect = [_MOCK_RESP_A, _MOCK_RESP_A]

        r = client.post(
            "/api/compare",
            json={
                "skill": "summarize",
                "version_a": "v0.0.1",
                "version_b": "v0.0.1",
                "inputs": {"text": "same"},
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["result_a"]["version"] == data["result_b"]["version"]


# ---------------------------------------------------------------------------
# Test: Compare Partial HTML Structure
# ---------------------------------------------------------------------------


class TestComparePartialHTMLStructure:
    def test_partial_returns_200(self, client: TestClient) -> None:
        r = client.get("/partials/compare")
        assert r.status_code == 200

    def test_partial_contains_compare_heading(self, client: TestClient) -> None:
        r = client.get("/partials/compare")
        assert "Compare" in r.text

    def test_partial_contains_skill_select(self, client: TestClient) -> None:
        r = client.get("/partials/compare")
        assert "compare-skill-select" in r.text

    def test_partial_contains_version_a_select(self, client: TestClient) -> None:
        r = client.get("/partials/compare")
        assert "compare-version-a" in r.text

    def test_partial_contains_version_b_select(self, client: TestClient) -> None:
        r = client.get("/partials/compare")
        assert "compare-version-b" in r.text

    def test_partial_contains_input_form(self, client: TestClient) -> None:
        r = client.get("/partials/compare")
        assert "compare-input-form" in r.text

    def test_partial_contains_model_input(self, client: TestClient) -> None:
        r = client.get("/partials/compare")
        assert "compare-model-input" in r.text

    def test_partial_contains_run_button(self, client: TestClient) -> None:
        r = client.get("/partials/compare")
        assert "compare-run-btn" in r.text

    def test_partial_contains_output_panels(self, client: TestClient) -> None:
        r = client.get("/partials/compare")
        assert "compare-output-a" in r.text
        assert "compare-output-b" in r.text

    def test_partial_contains_run_error_element(self, client: TestClient) -> None:
        r = client.get("/partials/compare")
        assert "compare-run-error" in r.text

    def test_partial_contains_diff_legend(self, client: TestClient) -> None:
        r = client.get("/partials/compare")
        assert "compare-diff-legend" in r.text

    def test_partial_references_versions_api(self, client: TestClient) -> None:
        r = client.get("/partials/compare")
        assert "/versions" in r.text

    def test_partial_references_compare_api(self, client: TestClient) -> None:
        r = client.get("/partials/compare")
        assert "/api/compare" in r.text

    def test_partial_contains_alpine_component(self, client: TestClient) -> None:
        r = client.get("/partials/compare")
        assert "compareSection()" in r.text

    def test_partial_contains_run_compare_fn(self, client: TestClient) -> None:
        r = client.get("/partials/compare")
        assert "runCompare" in r.text

    def test_partial_contains_diff_html_fn(self, client: TestClient) -> None:
        r = client.get("/partials/compare")
        assert "diffHtml" in r.text

    def test_partial_file_exists(self) -> None:
        assert (_STATIC_DIR / "partials" / "compare.html").exists()

    def test_partial_shows_ab_labels(self, client: TestClient) -> None:
        r = client.get("/partials/compare")
        assert '"a"' in r.text or "side 'a'" in r.text or "'a'" in r.text


# ---------------------------------------------------------------------------
# Test: Backward Compatibility (all prior endpoints still work)
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    def test_list_skills(self, client: TestClient) -> None:
        r = client.get("/api/skills")
        assert r.status_code == 200

    def test_get_skill(self, client: TestClient) -> None:
        r = client.get("/api/skills/summarize")
        assert r.status_code == 200

    def test_index_page(self, client: TestClient) -> None:
        r = client.get("/")
        assert r.status_code == 200

    def test_skills_partial(self, client: TestClient) -> None:
        r = client.get("/partials/skills")
        assert r.status_code == 200

    def test_harness_partial(self, client: TestClient) -> None:
        r = client.get("/partials/harness")
        assert r.status_code == 200

    def test_eval_partial(self, client: TestClient) -> None:
        r = client.get("/partials/eval")
        assert r.status_code == 200

    def test_logs_partial(self, client: TestClient) -> None:
        r = client.get("/partials/logs")
        assert r.status_code == 200

    def test_settings_partial(self, client: TestClient) -> None:
        r = client.get("/partials/settings")
        assert r.status_code == 200

    def test_compare_nav_item_in_index(self, client: TestClient) -> None:
        r = client.get("/")
        assert "compare" in r.text.lower()

    def test_openapi_docs(self, client: TestClient) -> None:
        r = client.get("/openapi.json")
        assert r.status_code == 200
        paths = r.json()["paths"]
        assert "/api/compare" in paths
        assert "/api/skills/{name}/versions" in paths
