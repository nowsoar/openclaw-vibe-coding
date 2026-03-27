"""数据源健康检查 API"""
import logging
from pathlib import Path

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sources", tags=["sources"])

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"


@router.get("")
def list_sources():
    """对所有已知数据源进行健康检查"""
    results = []
    _check_wechat(results)
    _check_rss(results)
    _check_web(results)
    _check_xiaohongshu(results)
    return results


@router.get("/templates")
def list_templates():
    """列出所有可用报告模板"""
    templates = []
    for p in sorted(_TEMPLATES_DIR.glob("*.yaml")):
        try:
            import yaml
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            templates.append({
                "id": p.stem,
                "name": data.get("name", p.stem),
                "description": data.get("description", ""),
            })
        except Exception:
            templates.append({"id": p.stem, "name": p.stem, "description": ""})
    return templates


@router.get("/templates/{template_id}")
def get_template(template_id: str):
    path = _TEMPLATES_DIR / f"{template_id}.yaml"
    if not path.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="模板不存在")
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ──────────────────────────────────────────────────────────────────────────────
# Health check helpers
# ──────────────────────────────────────────────────────────────────────────────

def _check_wechat(results: list):
    try:
        from researchkit.sources.wechat import WeChatSource
        src = WeChatSource(name="wechat", config={})
        ok, msg = src.health_check()
        results.append({"name": "wechat", "status": "ok" if ok else "warn", "message": msg})
    except Exception as exc:
        results.append({"name": "wechat", "status": "error", "message": str(exc)})


def _check_rss(results: list):
    try:
        from researchkit.sources.rss import RSSSource
        # RSS 无需凭证，简单检查依赖
        src = RSSSource(name="rss", config={"feeds": []})
        results.append({"name": "rss", "status": "ok", "message": "RSS 数据源就绪"})
    except Exception as exc:
        results.append({"name": "rss", "status": "error", "message": str(exc)})


def _check_web(results: list):
    try:
        from researchkit.sources.web import WebSource
        src = WebSource(name="web", config={})
        results.append({"name": "web", "status": "ok", "message": "Web 爬取数据源就绪"})
    except Exception as exc:
        results.append({"name": "web", "status": "error", "message": str(exc)})


def _check_xiaohongshu(results: list):
    try:
        from researchkit.sources.xiaohongshu import XiaohongshuSource
        src = XiaohongshuSource(name="xiaohongshu", config={})
        ok, msg = src.health_check()
        status = "ok" if ok else "warn"
        results.append({"name": "xiaohongshu", "status": status, "message": msg})
    except Exception as exc:
        results.append({"name": "xiaohongshu", "status": "error", "message": str(exc)})
