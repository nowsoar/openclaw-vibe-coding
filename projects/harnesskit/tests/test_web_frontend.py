"""Tests for Phase 8.2: Frontend framework (HTMX + Alpine.js + TailwindCSS CDN)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from harness_kit.config import init_harness
from harness_kit.web import create_app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


@pytest.fixture()
def client(workspace: Path) -> TestClient:
    return TestClient(create_app(base=workspace))


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _html(client: TestClient, path: str) -> str:
    """GET a URL and return the response text, asserting 200."""
    resp = client.get(path)
    assert resp.status_code == 200, f"{path} returned {resp.status_code}: {resp.text[:200]}"
    return resp.text


# ---------------------------------------------------------------------------
# Root page
# ---------------------------------------------------------------------------


class TestIndexPage:
    def test_root_returns_200(self, client: TestClient) -> None:
        assert client.get("/").status_code == 200

    def test_root_content_type_html(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "text/html" in resp.headers.get("content-type", "")

    def test_root_contains_page_title(self, client: TestClient) -> None:
        html = _html(client, "/")
        assert "HarnessKit" in html

    def test_tailwindcss_included(self, client: TestClient) -> None:
        html = _html(client, "/")
        # Accept both CDN and local bundled path
        assert "tailwind" in html.lower()

    def test_htmx_included(self, client: TestClient) -> None:
        html = _html(client, "/")
        # Accept both CDN and local bundled path
        assert "htmx" in html.lower()

    def test_alpinejs_included(self, client: TestClient) -> None:
        html = _html(client, "/")
        assert "alpine" in html.lower()

    def test_content_div_present(self, client: TestClient) -> None:
        """HTMX loads partials into id='content'."""
        html = _html(client, "/")
        assert 'id="content"' in html

    def test_default_htmx_load_skills(self, client: TestClient) -> None:
        """Main content area should trigger HTMX load for /partials/skills on page load."""
        html = _html(client, "/")
        assert "/partials/skills" in html

    def test_navigation_skills(self, client: TestClient) -> None:
        html = _html(client, "/")
        assert "skills" in html.lower()

    def test_navigation_harness(self, client: TestClient) -> None:
        html = _html(client, "/")
        assert "harness" in html.lower()

    def test_navigation_eval(self, client: TestClient) -> None:
        html = _html(client, "/")
        assert "eval" in html.lower()

    def test_navigation_logs(self, client: TestClient) -> None:
        html = _html(client, "/")
        assert "logs" in html.lower()

    def test_navigation_settings(self, client: TestClient) -> None:
        html = _html(client, "/")
        assert "settings" in html.lower()

    def test_htmx_get_attributes_present(self, client: TestClient) -> None:
        """Navigation buttons should carry hx-get attributes for dynamic routing."""
        html = _html(client, "/")
        assert "hx-get" in html

    def test_hx_target_content(self, client: TestClient) -> None:
        """HTMX target should be #content."""
        html = _html(client, "/")
        assert "hx-target" in html
        assert "#content" in html

    def test_alpinejs_x_data_attribute(self, client: TestClient) -> None:
        html = _html(client, "/")
        assert "x-data" in html


# ---------------------------------------------------------------------------
# HTMX partial pages
# ---------------------------------------------------------------------------


class TestPartialSkills:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/partials/skills").status_code == 200

    def test_content_type_html(self, client: TestClient) -> None:
        resp = client.get("/partials/skills")
        assert "text/html" in resp.headers.get("content-type", "")

    def test_contains_skills_heading(self, client: TestClient) -> None:
        html = _html(client, "/partials/skills")
        assert "skill" in html.lower()

    def test_uses_alpinejs_fetch(self, client: TestClient) -> None:
        """Skills Alpine component (now in index.html) should use fetch to load API data."""
        # Script moved from partial to index.html for HTMX compatibility
        index_html = _html(client, "/")
        partial_html = _html(client, "/partials/skills")
        combined = index_html + partial_html
        assert "fetch" in combined or "hx-get" in combined

    def test_references_api_skills(self, client: TestClient) -> None:
        # Script moved from partial to index.html for HTMX compatibility
        index_html = _html(client, "/")
        partial_html = _html(client, "/partials/skills")
        assert "/api/skills" in index_html + partial_html


class TestPartialHarness:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/partials/harness").status_code == 200

    def test_contains_harness_heading(self, client: TestClient) -> None:
        html = _html(client, "/partials/harness")
        assert "harness" in html.lower()


class TestPartialEval:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/partials/eval").status_code == 200

    def test_contains_eval_heading(self, client: TestClient) -> None:
        html = _html(client, "/partials/eval")
        assert "eval" in html.lower()


class TestPartialLogs:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/partials/logs").status_code == 200

    def test_contains_logs_heading(self, client: TestClient) -> None:
        html = _html(client, "/partials/logs")
        assert "log" in html.lower()


class TestPartialSettings:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/partials/settings").status_code == 200

    def test_contains_settings_heading(self, client: TestClient) -> None:
        html = _html(client, "/partials/settings")
        assert "setting" in html.lower()


class TestPartialNotFound:
    def test_unknown_section_returns_404(self, client: TestClient) -> None:
        assert client.get("/partials/nonexistent").status_code == 404

    def test_404_detail_message(self, client: TestClient) -> None:
        resp = client.get("/partials/bad-section")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Static file serving
# ---------------------------------------------------------------------------


class TestStaticFiles:
    def test_index_html_accessible_via_root(self, client: TestClient) -> None:
        """The static index.html is served at /."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "<!DOCTYPE html>" in resp.text or "<!doctype html>" in resp.text.lower()

    def test_all_five_partials_accessible(self, client: TestClient) -> None:
        for section in ("skills", "harness", "eval", "logs", "settings"):
            resp = client.get(f"/partials/{section}")
            assert resp.status_code == 200, f"/partials/{section} failed"


# ---------------------------------------------------------------------------
# Backward-compatibility: Phase 8.1 API routes still work
# ---------------------------------------------------------------------------


class TestPhase81CompatAPI:
    def test_api_skills_still_works(self, client: TestClient) -> None:
        resp = client.get("/api/skills")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_openapi_docs_still_work(self, client: TestClient) -> None:
        assert client.get("/openapi.json").status_code == 200

    def test_swagger_ui_still_works(self, client: TestClient) -> None:
        assert client.get("/docs").status_code == 200


# ---------------------------------------------------------------------------
# Static file structure (filesystem checks)
# ---------------------------------------------------------------------------


class TestStaticFileStructure:
    def test_static_dir_exists(self) -> None:
        from harness_kit.web import _STATIC_DIR
        assert _STATIC_DIR.exists(), "harness_kit/web/static/ must exist"

    def test_index_html_exists(self) -> None:
        from harness_kit.web import _STATIC_DIR
        assert (_STATIC_DIR / "index.html").exists()

    def test_partials_dir_exists(self) -> None:
        from harness_kit.web import _STATIC_DIR
        assert (_STATIC_DIR / "partials").is_dir()

    @pytest.mark.parametrize("section", ["skills", "harness", "eval", "logs", "settings"])
    def test_partial_file_exists(self, section: str) -> None:
        from harness_kit.web import _STATIC_DIR
        assert (_STATIC_DIR / "partials" / f"{section}.html").exists(), \
            f"partials/{section}.html missing"
