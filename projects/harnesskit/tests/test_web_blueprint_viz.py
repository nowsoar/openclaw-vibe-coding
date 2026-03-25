"""Tests for Phase 8.6: Blueprint Visualization (Web API + HTML partial)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from harness_kit.blueprint import save_blueprint
from harness_kit.config import init_harness
from harness_kit.web import _STATIC_DIR, create_app

# ---------------------------------------------------------------------------
# Sample blueprints
# ---------------------------------------------------------------------------

BP_SIMPLE: dict = {
    "name": "simple-pipeline",
    "description": "Lint then review",
    "inputs": [{"name": "file_path", "required": True}],
    "steps": [
        {
            "id": "lint",
            "type": "deterministic",
            "name": "Code Lint",
            "run": "flake8 {{inputs.file_path}}",
            "on_fail": "stop",
            "timeout": 10,
        },
        {
            "id": "review",
            "type": "agentic",
            "name": "AI Review",
            "skill": "code-reviewer@v0.1.0",
            "inputs": {"code": "{{steps.lint.output}}"},
            "max_retries": 2,
            "timeout": 60,
        },
    ],
    "outputs": {
        "lint_result": "{{steps.lint.output}}",
        "review_result": "{{steps.review.output}}",
    },
}

BP_NO_STEPS: dict = {
    "name": "empty-pipeline",
    "description": "Empty blueprint",
    "steps": [],
    "outputs": {},
}

BP_CONTINUE: dict = {
    "name": "continue-pipeline",
    "description": "Pipeline with continue on_fail",
    "steps": [
        {
            "id": "step-a",
            "type": "deterministic",
            "name": "Step A",
            "run": "echo hello",
            "on_fail": "continue",
        },
        {
            "id": "step-b",
            "type": "agentic",
            "name": "Step B",
            "harness": "my-harness@v0.1.0",
        },
    ],
    "outputs": {},
}

BP_GOTO: dict = {
    "name": "goto-pipeline",
    "description": "Pipeline with goto on_fail",
    "steps": [
        {
            "id": "step-x",
            "type": "deterministic",
            "name": "Step X",
            "run": "cmd1",
            "on_fail": "goto:step-z",
        },
        {
            "id": "step-y",
            "type": "deterministic",
            "name": "Step Y",
            "run": "cmd2",
        },
        {
            "id": "step-z",
            "type": "deterministic",
            "name": "Step Z",
            "run": "cmd3",
        },
    ],
    "outputs": {},
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def harness_dir(tmp_path: Path) -> Path:
    init_harness(base=tmp_path)
    return tmp_path


@pytest.fixture()
def client_with_blueprints(harness_dir: Path) -> TestClient:
    save_blueprint(
        name=BP_SIMPLE["name"],
        description=BP_SIMPLE["description"],
        inputs=BP_SIMPLE["inputs"],
        steps=BP_SIMPLE["steps"],
        outputs=BP_SIMPLE["outputs"],
        base=harness_dir,
    )
    save_blueprint(
        name=BP_CONTINUE["name"],
        description=BP_CONTINUE["description"],
        steps=BP_CONTINUE["steps"],
        outputs=BP_CONTINUE["outputs"],
        base=harness_dir,
    )
    app = create_app(base=harness_dir)
    return TestClient(app)


@pytest.fixture()
def client_empty(harness_dir: Path) -> TestClient:
    app = create_app(base=harness_dir)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests: GET /api/blueprints (list)
# ---------------------------------------------------------------------------


class TestListBlueprints:
    def test_returns_list(self, client_with_blueprints: TestClient) -> None:
        res = client_with_blueprints.get("/api/blueprints")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)

    def test_returns_metadata_fields(self, client_with_blueprints: TestClient) -> None:
        res = client_with_blueprints.get("/api/blueprints")
        names = [d["name"] for d in res.json()]
        assert "simple-pipeline" in names
        bp = next(d for d in res.json() if d["name"] == "simple-pipeline")
        assert "version" in bp
        assert "description" in bp
        assert "step_count" in bp
        assert bp["step_count"] == 2

    def test_empty_when_no_blueprints(self, client_empty: TestClient) -> None:
        res = client_empty.get("/api/blueprints")
        assert res.status_code == 200
        assert res.json() == []

    def test_multiple_blueprints(self, client_with_blueprints: TestClient) -> None:
        res = client_with_blueprints.get("/api/blueprints")
        assert len(res.json()) == 2


# ---------------------------------------------------------------------------
# Tests: GET /api/blueprints/{name} (detail)
# ---------------------------------------------------------------------------


class TestGetBlueprint:
    def test_returns_full_definition(self, client_with_blueprints: TestClient) -> None:
        res = client_with_blueprints.get("/api/blueprints/simple-pipeline")
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "simple-pipeline"
        assert "steps" in data
        assert len(data["steps"]) == 2

    def test_steps_have_correct_fields(self, client_with_blueprints: TestClient) -> None:
        res = client_with_blueprints.get("/api/blueprints/simple-pipeline")
        steps = res.json()["steps"]
        lint = next(s for s in steps if s["id"] == "lint")
        assert lint["type"] == "deterministic"
        assert "flake8" in lint.get("run", "")

    def test_outputs_included(self, client_with_blueprints: TestClient) -> None:
        res = client_with_blueprints.get("/api/blueprints/simple-pipeline")
        outputs = res.json().get("outputs", {})
        assert "lint_result" in outputs
        assert "review_result" in outputs

    def test_inputs_included(self, client_with_blueprints: TestClient) -> None:
        res = client_with_blueprints.get("/api/blueprints/simple-pipeline")
        inputs = res.json().get("inputs", [])
        assert any(i["name"] == "file_path" for i in inputs)

    def test_not_found_returns_404(self, client_empty: TestClient) -> None:
        res = client_empty.get("/api/blueprints/nonexistent")
        assert res.status_code == 404
        assert "nonexistent" in res.json()["detail"]


# ---------------------------------------------------------------------------
# Tests: GET /api/blueprints/{name}/graph (Mermaid)
# ---------------------------------------------------------------------------


class TestGetBlueprintGraph:
    def test_returns_mermaid_field(self, client_with_blueprints: TestClient) -> None:
        res = client_with_blueprints.get("/api/blueprints/simple-pipeline/graph")
        assert res.status_code == 200
        data = res.json()
        assert "mermaid" in data
        assert "name" in data
        assert data["name"] == "simple-pipeline"

    def test_mermaid_contains_flowchart(self, client_with_blueprints: TestClient) -> None:
        res = client_with_blueprints.get("/api/blueprints/simple-pipeline/graph")
        mermaid = res.json()["mermaid"]
        assert "flowchart" in mermaid

    def test_mermaid_contains_step_ids(self, client_with_blueprints: TestClient) -> None:
        res = client_with_blueprints.get("/api/blueprints/simple-pipeline/graph")
        mermaid = res.json()["mermaid"]
        assert "lint" in mermaid
        assert "review" in mermaid

    def test_mermaid_has_start_end_nodes(self, client_with_blueprints: TestClient) -> None:
        res = client_with_blueprints.get("/api/blueprints/simple-pipeline/graph")
        mermaid = res.json()["mermaid"]
        assert "__START__" in mermaid
        assert "__END__" in mermaid

    def test_mermaid_continue_on_fail(self, client_with_blueprints: TestClient) -> None:
        res = client_with_blueprints.get("/api/blueprints/continue-pipeline/graph")
        mermaid = res.json()["mermaid"]
        assert "continue" in mermaid or "-..->" in mermaid or "-.->|on fail: continue|" in mermaid

    def test_not_found_returns_404(self, client_empty: TestClient) -> None:
        res = client_empty.get("/api/blueprints/ghost/graph")
        assert res.status_code == 404

    def test_goto_on_fail_in_graph(self, harness_dir: Path) -> None:
        save_blueprint(
            name=BP_GOTO["name"],
            description=BP_GOTO["description"],
            steps=BP_GOTO["steps"],
            outputs=BP_GOTO["outputs"],
            base=harness_dir,
        )
        app = create_app(base=harness_dir)
        client = TestClient(app)
        res = client.get("/api/blueprints/goto-pipeline/graph")
        mermaid = res.json()["mermaid"]
        # goto edge should be present
        assert "fail" in mermaid or "goto" in mermaid or "step-z" in mermaid


# ---------------------------------------------------------------------------
# Tests: POST /api/blueprints/{name}/dry-run
# ---------------------------------------------------------------------------


class TestDryRunBlueprint:
    def test_returns_step_plan(self, client_with_blueprints: TestClient) -> None:
        res = client_with_blueprints.post("/api/blueprints/simple-pipeline/dry-run")
        assert res.status_code == 200
        data = res.json()
        assert data["dry_run"] is True
        assert "steps" in data
        assert data["step_count"] == 2

    def test_steps_have_status_pending(self, client_with_blueprints: TestClient) -> None:
        res = client_with_blueprints.post("/api/blueprints/simple-pipeline/dry-run")
        for step in res.json()["steps"]:
            assert step["status"] == "pending"

    def test_steps_have_action_field(self, client_with_blueprints: TestClient) -> None:
        res = client_with_blueprints.post("/api/blueprints/simple-pipeline/dry-run")
        steps = res.json()["steps"]
        lint = next(s for s in steps if s["id"] == "lint")
        assert "shell" in lint["action"] or "flake8" in lint["action"]
        review = next(s for s in steps if s["id"] == "review")
        assert "skill" in review["action"] or "code-reviewer" in review["action"]

    def test_blueprint_metadata_in_response(self, client_with_blueprints: TestClient) -> None:
        res = client_with_blueprints.post("/api/blueprints/simple-pipeline/dry-run")
        data = res.json()
        assert data["blueprint"] == "simple-pipeline"
        assert "version" in data

    def test_not_found_returns_404(self, client_empty: TestClient) -> None:
        res = client_empty.post("/api/blueprints/ghost/dry-run")
        assert res.status_code == 404

    def test_step_type_preserved(self, client_with_blueprints: TestClient) -> None:
        res = client_with_blueprints.post("/api/blueprints/simple-pipeline/dry-run")
        steps = res.json()["steps"]
        types = {s["id"]: s["type"] for s in steps}
        assert types["lint"] == "deterministic"
        assert types["review"] == "agentic"

    def test_harness_step_action(self, client_with_blueprints: TestClient) -> None:
        res = client_with_blueprints.post("/api/blueprints/continue-pipeline/dry-run")
        steps = res.json()["steps"]
        step_b = next(s for s in steps if s["id"] == "step-b")
        assert "harness" in step_b["action"]


# ---------------------------------------------------------------------------
# Tests: /partials/blueprints HTML structure
# ---------------------------------------------------------------------------


class TestBlueprintsPartialHTMLStructure:
    @pytest.fixture(autouse=True)
    def setup(self, client_empty: TestClient) -> None:
        self.client = client_empty

    def test_partial_returns_200(self) -> None:
        res = self.client.get("/partials/blueprints")
        assert res.status_code == 200

    def test_partial_contains_mermaid_cdn(self) -> None:
        html = (self._read_html())
        assert "mermaid" in html.lower()

    def test_partial_has_blueprint_list_id(self) -> None:
        html = self._read_html()
        assert 'id="blueprint-list"' in html

    def test_partial_has_detail_card_id(self) -> None:
        html = self._read_html()
        assert 'id="blueprint-detail-card"' in html

    def test_partial_has_graph_container_id(self) -> None:
        html = self._read_html()
        assert 'id="blueprint-graph-container"' in html

    def test_partial_has_step_table_id(self) -> None:
        html = self._read_html()
        assert 'id="blueprint-step-table"' in html

    def test_partial_has_dry_run_btn(self) -> None:
        html = self._read_html()
        assert 'id="blueprint-dry-run-btn"' in html

    def test_partial_has_dry_run_error_id(self) -> None:
        html = self._read_html()
        assert 'id="blueprint-dry-run-error"' in html

    def test_partial_has_search_input(self) -> None:
        html = self._read_html()
        assert 'id="blueprint-search"' in html

    def test_partial_has_empty_state(self) -> None:
        html = self._read_html()
        assert 'id="blueprint-empty"' in html

    def test_partial_has_outputs_section(self) -> None:
        html = self._read_html()
        assert 'id="blueprint-outputs"' in html

    def test_alpine_component_defined(self) -> None:
        html = self._read_html()
        assert "blueprintsSection()" in html

    def test_alpine_api_calls(self) -> None:
        html = self._read_html()
        assert "/api/blueprints" in html

    def test_dry_run_api_call(self) -> None:
        html = self._read_html()
        assert "dry-run" in html

    def test_graph_api_call(self) -> None:
        html = self._read_html()
        assert "/graph" in html

    def test_phase_badge(self) -> None:
        html = self._read_html()
        assert "8.6" in html

    def _read_html(self) -> str:
        return (_STATIC_DIR / "partials" / "blueprints.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests: index.html navigation includes Blueprints
# ---------------------------------------------------------------------------


class TestIndexBlueprintNav:
    @pytest.fixture(autouse=True)
    def setup(self, client_empty: TestClient) -> None:
        self.client = client_empty

    def test_blueprints_in_nav(self) -> None:
        index_html = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
        assert "blueprints" in index_html

    def test_blueprints_nav_label(self) -> None:
        index_html = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
        assert "Blueprints" in index_html

    def test_phase_badge_updated(self) -> None:
        index_html = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
        assert "Phase 8.6" in index_html


# ---------------------------------------------------------------------------
# Tests: Backwards compatibility (all prior endpoints still work)
# ---------------------------------------------------------------------------


class TestBackwardsCompatibility:
    def test_skills_list_still_works(self, client_empty: TestClient) -> None:
        res = client_empty.get("/api/skills")
        assert res.status_code == 200

    def test_eval_suites_still_works(self, client_empty: TestClient) -> None:
        res = client_empty.get("/api/eval/suites")
        assert res.status_code == 200

    def test_eval_results_still_works(self, client_empty: TestClient) -> None:
        res = client_empty.get("/api/eval/results")
        assert res.status_code == 200

    def test_eval_trend_still_works(self, client_empty: TestClient) -> None:
        res = client_empty.get("/api/eval/trend")
        assert res.status_code == 200

    def test_partials_all_work(self, client_empty: TestClient) -> None:
        for section in ["skills", "harness", "eval", "logs", "settings", "compare", "blueprints"]:
            res = client_empty.get(f"/partials/{section}")
            assert res.status_code == 200, f"/partials/{section} returned {res.status_code}"

    def test_index_still_works(self, client_empty: TestClient) -> None:
        res = client_empty.get("/")
        assert res.status_code == 200
