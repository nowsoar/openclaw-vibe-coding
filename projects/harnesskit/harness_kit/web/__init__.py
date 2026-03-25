"""HarnessKit Web — FastAPI server + HTMX/Alpine.js frontend (Phase 8.5)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

_STATIC_DIR = Path(__file__).parent / "static"

# ---------------------------------------------------------------------------
# Valid frontend sections
# ---------------------------------------------------------------------------

_SECTIONS = {"skills", "harness", "eval", "logs", "settings", "compare"}


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class SkillRunRequest(BaseModel):
    inputs: dict[str, str] = {}
    model: str | None = None


class SkillRunResponse(BaseModel):
    output: str
    model: str
    input_tokens: int
    output_tokens: int
    duration: float
    skill: str
    version: str


class CompareRequest(BaseModel):
    skill: str
    version_a: str
    version_b: str
    inputs: dict[str, str] = {}
    model: str | None = None


class CompareResponse(BaseModel):
    result_a: SkillRunResponse
    result_b: SkillRunResponse


class EvalRunRequest(BaseModel):
    target: str  # skill name to run against
    model: str | None = None


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(base: Path | None = None) -> FastAPI:
    """Create and return the FastAPI application.

    Parameters
    ----------
    base:
        Working directory used to locate the `.harness/` folder.
        Defaults to ``Path.cwd()`` at call time if *None*.
    """
    base_path: Path = base or Path.cwd()

    api = FastAPI(
        title="HarnessKit Web API",
        description="REST API for HarnessKit — manage and run AI Agent skills.",
        version="0.1.0",
    )

    # CORS — allow all origins so front-ends on any port can connect
    api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Dependency helpers (lazy import so fastapi is not required at
    # package import time)
    # ------------------------------------------------------------------

    def _list_skills() -> list[dict[str, Any]]:
        from harness_kit import skill as _skill_mod  # noqa: PLC0415

        return _skill_mod.list_skills(base=base_path)

    def _load_skill(name: str) -> dict[str, Any]:
        from harness_kit import skill as _skill_mod  # noqa: PLC0415

        return _skill_mod.load_skill(name, base=base_path)

    # ------------------------------------------------------------------
    # API Routes
    # ------------------------------------------------------------------

    @api.get("/api/skills", summary="List all skills")
    def list_skills() -> list[dict[str, Any]]:
        """Return metadata for every skill registered in the local .harness directory."""
        return _list_skills()

    @api.get("/api/skills/{name}", summary="Get skill details")
    def get_skill(name: str) -> dict[str, Any]:
        """Return the full definition of the named skill (current version)."""
        try:
            return _load_skill(name)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    @api.post("/api/skills/{name}/run", response_model=SkillRunResponse, summary="Run a skill")
    def run_skill(name: str, body: SkillRunRequest) -> SkillRunResponse:
        """Run a skill with the provided inputs and return the LLM response."""
        from harness_kit import skill as _skill_mod  # noqa: PLC0415
        from harness_kit.config import read_config  # noqa: PLC0415
        from harness_kit.llm import LLMConfig, build_messages, call_llm  # noqa: PLC0415

        # Load skill
        try:
            skill_data = _skill_mod.load_skill(name, base=base_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

        # Fill defaults for missing optional inputs
        vars_dict: dict[str, str] = dict(body.inputs)
        for inp in skill_data.get("inputs") or []:
            if inp.get("name") not in vars_dict:
                if inp.get("default") is not None:
                    vars_dict[inp["name"]] = str(inp["default"])
                elif inp.get("required", True):
                    raise HTTPException(
                        status_code=422,
                        detail=f"Missing required input: {inp['name']}",
                    )

        # Render assets
        try:
            rendered = _skill_mod.render_skill_prompt(name, base=base_path)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to render skill: {exc}")

        # Build LLM config
        try:
            cfg = read_config(base=base_path)
        except Exception:
            cfg = {}
        overrides: dict[str, Any] = {}
        if body.model:
            overrides["model"] = body.model
        llm_config = LLMConfig.from_harness_config(cfg, overrides=overrides)

        if not llm_config.api_key:
            raise HTTPException(
                status_code=503,
                detail="No API key configured. Set OPENAI_API_KEY or configure .harness/config.yaml.",
            )

        # Call LLM
        messages = build_messages(skill_data, rendered, vars_dict)
        try:
            resp = call_llm(messages, llm_config, stream=False)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}")

        return SkillRunResponse(
            output=resp.content,
            model=resp.model,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            duration=resp.duration,
            skill=skill_data.get("name", name),
            version=skill_data.get("version", ""),
        )

    def _run_one_version(
        name: str,
        version: str,
        inputs: dict[str, str],
        model_override: str | None,
    ) -> SkillRunResponse:
        """Run a single skill version; raises HTTPException on error."""
        from harness_kit import skill as _skill_mod  # noqa: PLC0415
        from harness_kit.config import read_config  # noqa: PLC0415
        from harness_kit.llm import LLMConfig, build_messages, call_llm  # noqa: PLC0415

        try:
            skill_data = _skill_mod.load_skill(name, version=version, base=base_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Skill '{name}@{version}' not found")

        vars_dict: dict[str, str] = dict(inputs)
        for inp in skill_data.get("inputs") or []:
            if inp.get("name") not in vars_dict:
                if inp.get("default") is not None:
                    vars_dict[inp["name"]] = str(inp["default"])
                elif inp.get("required", True):
                    raise HTTPException(
                        status_code=422,
                        detail=f"Missing required input: {inp['name']}",
                    )

        try:
            rendered = _skill_mod.render_skill_prompt(name, version=version, base=base_path)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to render skill: {exc}")

        try:
            cfg = read_config(base=base_path)
        except Exception:
            cfg = {}
        overrides: dict[str, Any] = {}
        if model_override:
            overrides["model"] = model_override
        llm_config = LLMConfig.from_harness_config(cfg, overrides=overrides)

        if not llm_config.api_key:
            raise HTTPException(
                status_code=503,
                detail="No API key configured. Set OPENAI_API_KEY or configure .harness/config.yaml.",
            )

        messages = build_messages(skill_data, rendered, vars_dict)
        try:
            resp = call_llm(messages, llm_config, stream=False)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}")

        return SkillRunResponse(
            output=resp.content,
            model=resp.model,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            duration=resp.duration,
            skill=skill_data.get("name", name),
            version=skill_data.get("version", version),
        )

    @api.get("/api/skills/{name}/versions", summary="List skill versions")
    def list_skill_versions(name: str) -> list[str]:
        """Return all available versions for the named skill, oldest first."""
        from harness_kit import skill as _skill_mod  # noqa: PLC0415

        versions = _skill_mod.list_versions(name, base=base_path)
        if not versions:
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
        return versions

    @api.post("/api/compare", response_model=CompareResponse, summary="A/B compare two skill versions")
    def compare_skills(body: CompareRequest) -> CompareResponse:
        """Run two versions of the same skill in parallel and return both results."""
        with ThreadPoolExecutor(max_workers=2) as pool:
            future_a = pool.submit(
                _run_one_version, body.skill, body.version_a, body.inputs, body.model
            )
            future_b = pool.submit(
                _run_one_version, body.skill, body.version_b, body.inputs, body.model
            )
            result_a = future_a.result()
            result_b = future_b.result()
        return CompareResponse(result_a=result_a, result_b=result_b)

    # ------------------------------------------------------------------
    # Eval API Routes (Phase 8.5)
    # ------------------------------------------------------------------

    @api.get("/api/eval/suites", summary="List all eval suites")
    def list_eval_suites() -> list[dict[str, Any]]:
        """Return summaries for every test suite in the local .harness directory."""
        from harness_kit import eval as _eval_mod  # noqa: PLC0415

        names = _eval_mod.list_suites(base=base_path)
        results: list[dict[str, Any]] = []
        for name in names:
            try:
                data = _eval_mod.load_suite(name, base=base_path)
                results.append(_eval_mod.suite_summary(data))
            except Exception:
                results.append({"name": name, "description": "", "case_count": 0, "assertion_count": 0})
        return results

    @api.get("/api/eval/suites/{name}", summary="Get eval suite details")
    def get_eval_suite(name: str) -> dict[str, Any]:
        """Return the full definition of the named test suite."""
        from harness_kit import eval as _eval_mod  # noqa: PLC0415

        try:
            return _eval_mod.load_suite(name, base=base_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Suite '{name}' not found")

    @api.post("/api/eval/suites/{name}/run", summary="Run an eval suite against a skill")
    def run_eval_suite(name: str, body: EvalRunRequest) -> dict[str, Any]:
        """Run a test suite against the specified skill and return the eval report."""
        from harness_kit import eval as _eval_mod  # noqa: PLC0415
        from harness_kit import skill as _skill_mod  # noqa: PLC0415
        from harness_kit.config import read_config  # noqa: PLC0415
        from harness_kit.llm import LLMConfig, build_messages, call_llm  # noqa: PLC0415

        # Validate suite exists
        try:
            _eval_mod.load_suite(name, base=base_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Suite '{name}' not found")

        # Validate skill exists
        try:
            skill_data = _skill_mod.load_skill(body.target, base=base_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Skill '{body.target}' not found")

        # Build LLM config
        try:
            cfg = read_config(base=base_path)
        except Exception:
            cfg = {}
        overrides: dict[str, Any] = {}
        if body.model:
            overrides["model"] = body.model
        llm_config = LLMConfig.from_harness_config(cfg, overrides=overrides)

        if not llm_config.api_key:
            raise HTTPException(
                status_code=503,
                detail="No API key configured. Set OPENAI_API_KEY or configure .harness/config.yaml.",
            )

        # Build rendered prompt once for this skill
        try:
            rendered = _skill_mod.render_skill_prompt(body.target, base=base_path)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to render skill: {exc}")

        def _invoke(inputs: dict[str, Any]) -> tuple[str, int, int, float]:
            vars_dict: dict[str, str] = {k: str(v) for k, v in inputs.items()}
            for inp in skill_data.get("inputs") or []:
                iname = inp.get("name")
                if iname and iname not in vars_dict and inp.get("default") is not None:
                    vars_dict[iname] = str(inp["default"])
            messages = build_messages(skill_data, rendered, vars_dict)
            resp = call_llm(messages, llm_config, stream=False)
            return resp.content, resp.input_tokens, resp.output_tokens, resp.duration

        try:
            target_label = f"{body.target}@{skill_data.get('version', 'current')}"
            report = _eval_mod.run_eval(
                target=target_label,
                suite_name=name,
                invoke_fn=_invoke,
                base=base_path,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Eval run failed: {exc}")

        return report

    @api.get("/api/eval/results", summary="List recent eval results")
    def list_eval_results(limit: int = 20) -> list[dict[str, Any]]:
        """Return recent eval results sorted by timestamp descending."""
        from harness_kit import eval as _eval_mod  # noqa: PLC0415

        all_results = _eval_mod.load_results(base=base_path)
        # Sort descending by timestamp, return last `limit`
        recent = list(reversed(all_results[-limit:]))
        return [
            {
                "timestamp": r.get("timestamp", ""),
                "target": r.get("target", ""),
                "suite": r.get("suite", ""),
                "summary": r.get("summary", {}),
            }
            for r in recent
        ]

    @api.get("/api/eval/trend", summary="Get eval pass-rate trend")
    def get_eval_trend(
        target: str | None = None,
        suite: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return historical pass-rate trend data for charting."""
        from harness_kit import eval as _eval_mod  # noqa: PLC0415

        return _eval_mod.eval_trend(
            target_filter=target,
            suite_filter=suite,
            base=base_path,
            limit=limit,
        )

    # ------------------------------------------------------------------

    # Mount static files under /static/
    if _STATIC_DIR.exists():
        api.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @api.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index() -> FileResponse:
        """Serve the main SPA shell."""
        return FileResponse(str(_STATIC_DIR / "index.html"))

    @api.get("/partials/{section}", response_class=HTMLResponse, include_in_schema=False)
    def get_partial(section: str) -> FileResponse:
        """Serve an HTMX partial page for the given section."""
        if section not in _SECTIONS:
            raise HTTPException(status_code=404, detail=f"Section '{section}' not found")
        partial_file = _STATIC_DIR / "partials" / f"{section}.html"
        if not partial_file.exists():
            raise HTTPException(status_code=404, detail=f"Partial '{section}' not found")
        return FileResponse(str(partial_file))

    return api
