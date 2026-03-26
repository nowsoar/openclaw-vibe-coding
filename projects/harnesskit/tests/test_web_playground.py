"""Tests for Phase 8.3: Prompt Playground (Web UI + API integration)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient

from harness_kit.config import init_harness
from harness_kit.web import create_app

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SKILL_WITH_INPUTS: dict = {
    "name": "translate",
    "description": "Translate text to another language",
    "trigger": "When translation is needed",
    "inputs": [
        {"name": "text", "type": "string", "required": True},
        {"name": "target_lang", "type": "string", "required": False, "default": "English"},
    ],
    "outputs": [{"name": "translation", "type": "string"}],
    "assets": {},
    "examples": [],
    "changelog": "initial",
}

SKILL_NO_INPUTS: dict = {
    "name": "ping",
    "description": "A simple ping skill",
    "trigger": "ping",
    "inputs": [],
    "outputs": [{"name": "reply", "type": "string"}],
    "assets": {},
    "examples": [],
    "changelog": "initial",
}


def _write_skill(workspace: Path, skill_data: dict) -> None:
    """Helper: write a skill YAML into the workspace."""
    name = skill_data["name"]
    skill_dir = workspace / ".harness" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    data = {**skill_data, "version": "v0.0.1"}
    (skill_dir / "v0.0.1.yaml").write_text(yaml.dump(data), encoding="utf-8")
    (skill_dir / "_current").write_text("v0.0.1", encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


@pytest.fixture()
def workspace_with_skills(workspace: Path) -> Path:
    _write_skill(workspace, SKILL_WITH_INPUTS)
    _write_skill(workspace, SKILL_NO_INPUTS)
    return workspace


@pytest.fixture()
def client(workspace_with_skills: Path) -> TestClient:
    return TestClient(create_app(base=workspace_with_skills))


@pytest.fixture()
def client_empty(workspace: Path) -> TestClient:
    return TestClient(create_app(base=workspace))


# ---------------------------------------------------------------------------
# 1. Playground HTML structure
# ---------------------------------------------------------------------------


class TestPlaygroundHTMLStructure:
    """Verify the skills partial contains all Playground UI elements."""

    def test_skills_partial_returns_200(self, client: TestClient) -> None:
        resp = client.get("/partials/skills")
        assert resp.status_code == 200

    def test_skills_partial_is_html(self, client: TestClient) -> None:
        resp = client.get("/partials/skills")
        assert "text/html" in resp.headers["content-type"]

    def test_playground_header_present(self, client: TestClient) -> None:
        resp = client.get("/partials/skills")
        assert "Playground" in resp.text or "playground" in resp.text.lower()

    def test_input_form_section_present(self, client: TestClient) -> None:
        resp = client.get("/partials/skills")
        assert "playground-input-form" in resp.text

    def test_model_selector_present(self, client: TestClient) -> None:
        resp = client.get("/partials/skills")
        assert "playground-model-selector" in resp.text

    def test_run_button_present(self, client: TestClient) -> None:
        resp = client.get("/partials/skills")
        assert "playground-run-btn" in resp.text

    def test_output_area_present(self, client: TestClient) -> None:
        resp = client.get("/partials/skills")
        assert "playground-output" in resp.text

    def test_run_error_area_present(self, client: TestClient) -> None:
        resp = client.get("/partials/skills")
        assert "playground-run-error" in resp.text

    def test_skill_list_panel_present(self, client: TestClient) -> None:
        resp = client.get("/partials/skills")
        assert "skill-list" in resp.text

    def test_skill_playground_panel_present(self, client: TestClient) -> None:
        resp = client.get("/partials/skills")
        assert "skill-playground" in resp.text

    def test_alpine_openplayground_function(self, client: TestClient) -> None:
        resp = client.get("/partials/skills")
        assert "openPlayground" in resp.text

    def test_alpine_runskill_function(self, client: TestClient) -> None:
        resp = client.get("/partials/skills")
        assert "runSkill" in resp.text

    def test_api_skills_reference(self, client: TestClient) -> None:
        # Script moved from partial to index.html for HTMX compatibility
        combined = client.get("/partials/skills").text + client.get("/").text
        assert "/api/skills" in combined

    def test_api_run_endpoint_referenced(self, client: TestClient) -> None:
        # Script moved from partial to index.html for HTMX compatibility
        combined = client.get("/partials/skills").text + client.get("/").text
        assert "/run" in combined

    def test_model_input_placeholder(self, client: TestClient) -> None:
        resp = client.get("/partials/skills")
        # Should mention model name examples or "default"
        assert "gpt" in resp.text.lower() or "model" in resp.text.lower()

    def test_inputs_template_loop(self, client: TestClient) -> None:
        resp = client.get("/partials/skills")
        # Alpine.js template loop over inputs
        assert "x-for" in resp.text
        assert "inp" in resp.text

    def test_output_token_stats_displayed(self, client: TestClient) -> None:
        resp = client.get("/partials/skills")
        # Stats area should reference token counts and duration
        assert "input_tokens" in resp.text or "Tokens" in resp.text

    def test_output_pre_element_present(self, client: TestClient) -> None:
        resp = client.get("/partials/skills")
        assert "<pre" in resp.text

    def test_static_file_exists(self, tmp_path: Path) -> None:
        from harness_kit.web import _STATIC_DIR
        partial = _STATIC_DIR / "partials" / "skills.html"
        assert partial.exists()
        content = partial.read_text(encoding="utf-8")
        assert "playground" in content.lower()


# ---------------------------------------------------------------------------
# 2. API: GET /api/skills/{name} — returns inputs field
# ---------------------------------------------------------------------------


class TestSkillDetailAPI:
    """The detail endpoint must expose the inputs array for form generation."""

    def test_get_skill_returns_inputs_field(self, client: TestClient) -> None:
        resp = client.get("/api/skills/translate")
        assert resp.status_code == 200
        data = resp.json()
        assert "inputs" in data

    def test_get_skill_inputs_have_name(self, client: TestClient) -> None:
        resp = client.get("/api/skills/translate")
        inputs = resp.json()["inputs"]
        names = [i["name"] for i in inputs]
        assert "text" in names
        assert "target_lang" in names

    def test_get_skill_inputs_have_required_flag(self, client: TestClient) -> None:
        resp = client.get("/api/skills/translate")
        inputs = resp.json()["inputs"]
        text_inp = next(i for i in inputs if i["name"] == "text")
        assert text_inp["required"] is True

    def test_get_skill_inputs_have_default(self, client: TestClient) -> None:
        resp = client.get("/api/skills/translate")
        inputs = resp.json()["inputs"]
        lang_inp = next(i for i in inputs if i["name"] == "target_lang")
        assert lang_inp.get("default") == "English"

    def test_get_skill_no_inputs_returns_empty_list(self, client: TestClient) -> None:
        resp = client.get("/api/skills/ping")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("inputs") == [] or data.get("inputs") is None

    def test_get_nonexistent_skill_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/skills/nonexistent-skill")
        assert resp.status_code == 404

    def test_get_skill_returns_description(self, client: TestClient) -> None:
        resp = client.get("/api/skills/translate")
        data = resp.json()
        assert data.get("description") == SKILL_WITH_INPUTS["description"]

    def test_get_skill_returns_version(self, client: TestClient) -> None:
        resp = client.get("/api/skills/translate")
        data = resp.json()
        assert data.get("version") == "v0.0.1"


# ---------------------------------------------------------------------------
# 3. API: POST /api/skills/{name}/run — Playground run endpoint
# ---------------------------------------------------------------------------


MOCK_LLM_RESPONSE = MagicMock(
    content="Translated: Hello World",
    model="gpt-4o",
    input_tokens=50,
    output_tokens=10,
    duration=1.2,
)


class TestRunSkillPlayground:
    """End-to-end run tests for the Playground."""

    def test_run_skill_missing_skill_returns_404(self, client: TestClient) -> None:
        resp = client.post(
            "/api/skills/no-such-skill/run",
            json={"inputs": {}},
        )
        assert resp.status_code == 404

    def test_run_skill_missing_required_input_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/api/skills/translate/run",
            json={"inputs": {}},  # 'text' is required
        )
        assert resp.status_code == 422

    def test_run_skill_missing_required_input_has_detail(self, client: TestClient) -> None:
        resp = client.post(
            "/api/skills/translate/run",
            json={"inputs": {}},
        )
        assert "text" in resp.json()["detail"].lower()

    def test_run_skill_no_api_key_returns_503(self, client: TestClient) -> None:
        """Without an API key the endpoint must return 503."""
        with patch("harness_kit.llm.LLMConfig.from_harness_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(api_key=None)
            resp = client.post(
                "/api/skills/translate/run",
                json={"inputs": {"text": "Hello"}},
            )
        assert resp.status_code == 503

    def test_run_skill_success_with_mocked_llm(self, client: TestClient) -> None:
        with (
            patch("harness_kit.llm.call_llm", return_value=MOCK_LLM_RESPONSE),
            patch("harness_kit.llm.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="sk-test")
            resp = client.post(
                "/api/skills/translate/run",
                json={"inputs": {"text": "Hello"}},
            )
        assert resp.status_code == 200

    def test_run_skill_response_has_output(self, client: TestClient) -> None:
        with (
            patch("harness_kit.llm.call_llm", return_value=MOCK_LLM_RESPONSE),
            patch("harness_kit.llm.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="sk-test")
            resp = client.post(
                "/api/skills/translate/run",
                json={"inputs": {"text": "Hello"}},
            )
        data = resp.json()
        assert data["output"] == "Translated: Hello World"

    def test_run_skill_response_has_model(self, client: TestClient) -> None:
        with (
            patch("harness_kit.llm.call_llm", return_value=MOCK_LLM_RESPONSE),
            patch("harness_kit.llm.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="sk-test")
            resp = client.post(
                "/api/skills/translate/run",
                json={"inputs": {"text": "Hello"}},
            )
        data = resp.json()
        assert data["model"] == "gpt-4o"

    def test_run_skill_response_has_token_counts(self, client: TestClient) -> None:
        with (
            patch("harness_kit.llm.call_llm", return_value=MOCK_LLM_RESPONSE),
            patch("harness_kit.llm.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="sk-test")
            resp = client.post(
                "/api/skills/translate/run",
                json={"inputs": {"text": "Hello"}},
            )
        data = resp.json()
        assert "input_tokens" in data
        assert "output_tokens" in data

    def test_run_skill_response_has_duration(self, client: TestClient) -> None:
        with (
            patch("harness_kit.llm.call_llm", return_value=MOCK_LLM_RESPONSE),
            patch("harness_kit.llm.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="sk-test")
            resp = client.post(
                "/api/skills/translate/run",
                json={"inputs": {"text": "Hello"}},
            )
        data = resp.json()
        assert "duration" in data
        assert isinstance(data["duration"], float)

    def test_run_skill_response_has_skill_name(self, client: TestClient) -> None:
        with (
            patch("harness_kit.llm.call_llm", return_value=MOCK_LLM_RESPONSE),
            patch("harness_kit.llm.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="sk-test")
            resp = client.post(
                "/api/skills/translate/run",
                json={"inputs": {"text": "Hello"}},
            )
        data = resp.json()
        assert data["skill"] == "translate"

    def test_run_skill_with_model_override(self, client: TestClient) -> None:
        custom_resp = MagicMock(
            content="output",
            model="claude-3-5-sonnet",
            input_tokens=20,
            output_tokens=5,
            duration=0.5,
        )
        with (
            patch("harness_kit.llm.call_llm", return_value=custom_resp),
            patch("harness_kit.llm.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="sk-test")
            resp = client.post(
                "/api/skills/translate/run",
                json={"inputs": {"text": "Hello"}, "model": "claude-3-5-sonnet"},
            )
        assert resp.status_code == 200
        assert resp.json()["model"] == "claude-3-5-sonnet"

    def test_run_skill_with_optional_default_filled(self, client: TestClient) -> None:
        """Optional input with default should not require explicit value."""
        with (
            patch("harness_kit.llm.call_llm", return_value=MOCK_LLM_RESPONSE),
            patch("harness_kit.llm.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="sk-test")
            # Only provide required 'text'; 'target_lang' has default "English"
            resp = client.post(
                "/api/skills/translate/run",
                json={"inputs": {"text": "Hola"}},
            )
        assert resp.status_code == 200

    def test_run_skill_no_inputs_skill_success(self, client: TestClient) -> None:
        """A skill with no inputs should run with an empty inputs dict."""
        with (
            patch("harness_kit.llm.call_llm", return_value=MOCK_LLM_RESPONSE),
            patch("harness_kit.llm.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="sk-test")
            resp = client.post(
                "/api/skills/ping/run",
                json={"inputs": {}},
            )
        assert resp.status_code == 200

    def test_run_skill_llm_failure_returns_502(self, client: TestClient) -> None:
        with (
            patch("harness_kit.llm.call_llm", side_effect=RuntimeError("LLM down")),
            patch("harness_kit.llm.LLMConfig.from_harness_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(api_key="sk-test")
            resp = client.post(
                "/api/skills/translate/run",
                json={"inputs": {"text": "Hello"}},
            )
        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# 4. Phase 8.1 + 8.2 backwards compatibility
# ---------------------------------------------------------------------------


class TestBackwardsCompat:
    """Phase 8.3 must not break existing Phase 8.1 / 8.2 functionality."""

    def test_list_skills_api_still_works(self, client: TestClient) -> None:
        resp = client.get("/api/skills")
        assert resp.status_code == 200

    def test_openapi_json_still_works(self, client: TestClient) -> None:
        resp = client.get("/openapi.json")
        assert resp.status_code == 200

    def test_docs_still_works(self, client: TestClient) -> None:
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_index_page_still_loads(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200

    def test_all_partials_still_accessible(self, client: TestClient) -> None:
        for section in ("skills", "harness", "eval", "logs", "settings"):
            resp = client.get(f"/partials/{section}")
            assert resp.status_code == 200, f"Partial '{section}' returned {resp.status_code}"

    def test_unknown_partial_still_404(self, client: TestClient) -> None:
        resp = client.get("/partials/unknown-section")
        assert resp.status_code == 404
