"""Tests for Phase 8.1: Web service framework (FastAPI + uvicorn)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from harness_kit.cli import app as cli_app
from harness_kit.config import init_harness
from harness_kit.web import create_app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SKILL: dict = {
    "name": "hello-skill",
    "description": "A simple greeting skill",
    "trigger": "When you want a greeting",
    "inputs": [
        {"name": "name", "type": "string", "required": True},
    ],
    "outputs": [{"name": "greeting", "type": "string"}],
    "assets": {},
    "examples": [],
    "changelog": "initial version",
}


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Initialised .harness workspace in tmp_path."""
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


@pytest.fixture()
def workspace_with_skill(workspace: Path) -> Path:
    """Workspace with one skill pre-populated."""
    skill_dir = workspace / ".harness" / "skills" / "hello-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_data = {**SAMPLE_SKILL, "version": "v0.0.1"}
    (skill_dir / "v0.0.1.yaml").write_text(yaml.dump(skill_data), encoding="utf-8")
    (skill_dir / "_current").write_text("v0.0.1", encoding="utf-8")
    return workspace


@pytest.fixture()
def client_empty(workspace: Path) -> TestClient:
    """TestClient with an empty .harness workspace."""
    web = create_app(base=workspace)
    return TestClient(web)


@pytest.fixture()
def client_with_skill(workspace_with_skill: Path) -> TestClient:
    """TestClient with a workspace that has one skill."""
    web = create_app(base=workspace_with_skill)
    return TestClient(web)


# ---------------------------------------------------------------------------
# 1. App creation
# ---------------------------------------------------------------------------


class TestAppCreation:
    def test_create_app_returns_fastapi(self, tmp_path: Path) -> None:
        from fastapi import FastAPI

        web = create_app(base=tmp_path)
        assert isinstance(web, FastAPI)

    def test_create_app_default_base(self) -> None:
        """create_app() should not raise when called without base arg."""
        from fastapi import FastAPI

        web = create_app()
        assert isinstance(web, FastAPI)

    def test_app_title(self, tmp_path: Path) -> None:
        web = create_app(base=tmp_path)
        assert "HarnessKit" in web.title


# ---------------------------------------------------------------------------
# 2. GET /api/skills
# ---------------------------------------------------------------------------


class TestListSkills:
    def test_empty_workspace_returns_empty_list(self, client_empty: TestClient) -> None:
        response = client_empty.get("/api/skills")
        assert response.status_code == 200
        assert response.json() == []

    def test_with_skill_returns_list(self, client_with_skill: TestClient) -> None:
        response = client_with_skill.get("/api/skills")
        assert response.status_code == 200
        skills = response.json()
        assert isinstance(skills, list)
        assert len(skills) == 1
        assert skills[0]["name"] == "hello-skill"

    def test_response_is_json(self, client_empty: TestClient) -> None:
        response = client_empty.get("/api/skills")
        assert "application/json" in response.headers["content-type"]

    def test_skill_has_expected_fields(self, client_with_skill: TestClient) -> None:
        response = client_with_skill.get("/api/skills")
        skill = response.json()[0]
        assert "name" in skill
        assert "description" in skill
        assert "version" in skill


# ---------------------------------------------------------------------------
# 3. GET /api/skills/{name}
# ---------------------------------------------------------------------------


class TestGetSkill:
    def test_existing_skill_returns_200(self, client_with_skill: TestClient) -> None:
        response = client_with_skill.get("/api/skills/hello-skill")
        assert response.status_code == 200

    def test_existing_skill_body(self, client_with_skill: TestClient) -> None:
        response = client_with_skill.get("/api/skills/hello-skill")
        data = response.json()
        assert data["name"] == "hello-skill"
        assert data["description"] == "A simple greeting skill"

    def test_nonexistent_skill_returns_404(self, client_empty: TestClient) -> None:
        response = client_empty.get("/api/skills/does-not-exist")
        assert response.status_code == 404

    def test_404_contains_skill_name(self, client_empty: TestClient) -> None:
        response = client_empty.get("/api/skills/ghost-skill")
        assert response.status_code == 404
        assert "ghost-skill" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 4. POST /api/skills/{name}/run
# ---------------------------------------------------------------------------


class TestRunSkill:
    def test_run_nonexistent_skill_returns_404(self, client_empty: TestClient) -> None:
        response = client_empty.post("/api/skills/no-skill/run", json={"inputs": {}})
        assert response.status_code == 404

    def test_run_missing_required_input_returns_422(
        self, client_with_skill: TestClient
    ) -> None:
        # hello-skill requires 'name', so send empty inputs
        response = client_with_skill.post(
            "/api/skills/hello-skill/run", json={"inputs": {}}
        )
        assert response.status_code == 422

    def test_run_no_api_key_returns_503(
        self, client_with_skill: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        response = client_with_skill.post(
            "/api/skills/hello-skill/run",
            json={"inputs": {"name": "Alice"}},
        )
        assert response.status_code == 503

    def test_run_with_llm_mock_returns_200(
        self, client_with_skill: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mock the LLM call and verify the response shape."""
        from harness_kit.llm import LLMResponse

        fake_resp = LLMResponse(
            content="Hello, Alice!",
            model="gpt-4o-mock",
            input_tokens=10,
            output_tokens=5,
            duration=0.1,
        )

        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        with patch("harness_kit.llm.call_llm", return_value=fake_resp):
            # Also patch render to avoid resolving missing asset refs
            with patch(
                "harness_kit.skill.render_skill_prompt",
                return_value={"system": "", "user": "Hello {{name}}", "context": "", "rules": "", "schemas": ""},
            ):
                response = client_with_skill.post(
                    "/api/skills/hello-skill/run",
                    json={"inputs": {"name": "Alice"}},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["output"] == "Hello, Alice!"
        assert data["model"] == "gpt-4o-mock"
        assert data["input_tokens"] == 10
        assert data["output_tokens"] == 5
        assert "duration" in data
        assert data["skill"] == "hello-skill"

    def test_run_accepts_model_override(
        self, client_with_skill: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from harness_kit.llm import LLMResponse

        fake_resp = LLMResponse(
            content="Hi!",
            model="gpt-3.5-turbo",
            input_tokens=5,
            output_tokens=3,
            duration=0.05,
        )
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        with patch("harness_kit.llm.call_llm", return_value=fake_resp):
            with patch(
                "harness_kit.skill.render_skill_prompt",
                return_value={"system": "", "user": "", "context": "", "rules": "", "schemas": ""},
            ):
                response = client_with_skill.post(
                    "/api/skills/hello-skill/run",
                    json={"inputs": {"name": "Bob"}, "model": "gpt-3.5-turbo"},
                )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 5. CORS headers
# ---------------------------------------------------------------------------


class TestCORS:
    def test_cors_preflight_allows_all(self, client_empty: TestClient) -> None:
        response = client_empty.options(
            "/api/skills",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # FastAPI + CORSMiddleware should return 200 with an allow-origin header
        assert response.status_code == 200
        allow_origin = response.headers.get("access-control-allow-origin")
        # Starlette reflects the origin (or '*') — either is valid CORS
        assert allow_origin is not None

    def test_cors_header_on_get(self, client_empty: TestClient) -> None:
        response = client_empty.get(
            "/api/skills",
            headers={"Origin": "http://example.com"},
        )
        # CORS middleware should set an allow-origin header
        allow_origin = response.headers.get("access-control-allow-origin")
        assert allow_origin is not None


# ---------------------------------------------------------------------------
# 6. OpenAPI docs endpoint
# ---------------------------------------------------------------------------


class TestOpenAPIDocs:
    def test_openapi_schema_available(self, client_empty: TestClient) -> None:
        response = client_empty.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "paths" in schema
        assert "/api/skills" in schema["paths"]
        assert "/api/skills/{name}" in schema["paths"]
        assert "/api/skills/{name}/run" in schema["paths"]

    def test_docs_ui_available(self, client_empty: TestClient) -> None:
        response = client_empty.get("/docs")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 7. CLI: serve command is registered
# ---------------------------------------------------------------------------


class TestServeCLI:
    def test_serve_command_exists(self) -> None:
        result = runner.invoke(cli_app, ["serve", "--help"])
        assert result.exit_code == 0
        assert "serve" in result.output.lower() or "uvicorn" in result.output.lower() or "--host" in result.output

    def test_serve_help_shows_options(self) -> None:
        result = runner.invoke(cli_app, ["serve", "--help"])
        assert result.exit_code == 0
        assert "--host" in result.output
        assert "--port" in result.output
