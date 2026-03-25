"""HarnessKit Web — FastAPI server + HTMX/Alpine.js frontend (Phase 8.2)."""

from __future__ import annotations

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

_SECTIONS = {"skills", "harness", "eval", "logs", "settings"}


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

    # ------------------------------------------------------------------
    # Frontend routes (Phase 8.2)
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
