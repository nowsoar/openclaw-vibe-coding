"""ResearchKit Web Backend — FastAPI 服务"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel as _BaseModel

from .schemas import (
    TaskCreate,
    TaskResponse,
    TaskStatus,
    SourceStatusResponse,
    ProgressEvent,
)
from .storage import TaskStore
from .database import init_db, get_db
from .routers.auth import router as auth_router, get_current_user
from .routers.organizations import router as orgs_router
from .scheduler import scheduler as _scheduler

logger = logging.getLogger(__name__)

app = FastAPI(
    title="ResearchKit API",
    description="AI 驱动的自动化调研平台 — Web API",
    version="1.0.0",
)

# CORS — 允许前端开发服务器访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = TaskStore()

# WebSocket 连接管理
_ws_connections: dict[str, list[WebSocket]] = {}


@app.on_event("startup")
async def startup():
    init_db()
    _scheduler.start()


@app.on_event("shutdown")
async def shutdown():
    _scheduler.shutdown(wait=False)


# 注册认证路由
app.include_router(auth_router)
# 注册组织路由
app.include_router(orgs_router)


# ─── 任务管理 CRUD ──────────────────────────────────────────────────────────

@app.get("/api/tasks", response_model=list[TaskResponse])
async def list_tasks(current_user=Depends(get_current_user)):
    tasks = store.list_tasks()
    if current_user:
        tasks = [t for t in tasks if t.get("user_id") == current_user.id]
    return tasks


@app.post("/api/tasks", response_model=TaskResponse, status_code=201)
async def create_task(body: TaskCreate, current_user=Depends(get_current_user)):
    task = store.create_task(body)
    if current_user:
        store.update_task(task["id"], {"user_id": current_user.id})
        task["user_id"] = current_user.id
    return task


@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, current_user=Depends(get_current_user)):
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if current_user and task.get("user_id") and task["user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    return task


@app.delete("/api/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str, current_user=Depends(get_current_user)):
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if current_user and task.get("user_id") and task["user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除此任务")
    store.delete_task(task_id)


@app.post("/api/tasks/{task_id}/run", response_model=TaskResponse)
async def run_task(task_id: str, current_user=Depends(get_current_user)):
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if current_user and task.get("user_id") and task["user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="无权运行此任务")
    if task["status"] == TaskStatus.RUNNING:
        raise HTTPException(status_code=409, detail="任务正在运行中")

    store.update_task(task_id, {"status": TaskStatus.RUNNING, "started_at": datetime.now().isoformat()})
    asyncio.create_task(_run_pipeline(task_id, task))
    return store.get_task(task_id)


@app.get("/api/tasks/{task_id}/report")
async def get_report(task_id: str):
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    report_path = task.get("report_path")
    if not report_path or not Path(report_path).exists():
        raise HTTPException(status_code=404, detail="报告不存在")
    content = Path(report_path).read_text(encoding="utf-8")
    return {"content": content, "path": report_path}


# ─── 数据源管理 ──────────────────────────────────────────────────────────────

@app.get("/api/sources", response_model=list[SourceStatusResponse])
async def get_sources():
    from researchkit.core.config import load_sources_config
    from researchkit.sources.wechat import WeChatSource
    from researchkit.sources.rss import RSSSource
    from researchkit.sources.web import WebSource

    try:
        sources_cfg = load_sources_config()
    except Exception:
        sources_cfg = {}

    checks = {
        "wechat": (WeChatSource, sources_cfg.get("wechat", {})),
        "rss": (RSSSource, sources_cfg.get("rss", {})),
        "web": (WebSource, sources_cfg.get("web", {})),
    }

    result = []
    for name, (cls, cfg) in checks.items():
        src = cls(name=name, config=cfg)
        ok, msg = src.health_check()
        result.append(SourceStatusResponse(name=name, status="ok" if ok else "error", message=msg))
    return result


# ─── 模板管理 ────────────────────────────────────────────────────────────────

@app.get("/api/templates")
async def list_templates():
    templates_dir = Path(__file__).parent.parent.parent / "templates"
    result = []
    for yaml_file in sorted(templates_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
            result.append({
                "id": yaml_file.stem,
                "name": data.get("name", yaml_file.stem),
                "description": data.get("description", ""),
            })
        except Exception:
            pass
    return result


@app.get("/api/templates/{template_id}")
async def get_template(template_id: str):
    templates_dir = Path(__file__).parent.parent.parent / "templates"
    path = templates_dir / f"{template_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="模板不存在")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {"id": template_id, **data}


@app.put("/api/templates/{template_id}")
async def update_template(template_id: str, body: dict):
    templates_dir = Path(__file__).parent.parent.parent / "templates"
    path = templates_dir / f"{template_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="模板不存在")
    path.write_text(yaml.dump(body, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    return {"id": template_id, **body}


class ScheduleCreate(_BaseModel):
    task_id: str
    task_config: dict
    cron_expr: str
    incremental: bool = False
    notification_config: Optional[dict] = None


# ─── 定时任务管理 ─────────────────────────────────────────────────────────────

@app.get("/api/schedules")
async def list_schedules(current_user=Depends(get_current_user)):
    return _scheduler.list_tasks()


@app.post("/api/schedules", status_code=201)
async def create_schedule(body: ScheduleCreate, current_user=Depends(get_current_user)):
    try:
        return _scheduler.add_task(
            task_id=body.task_id,
            task_config=body.task_config,
            cron_expr=body.cron_expr,
            incremental=body.incremental,
            notification_config=body.notification_config,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/schedules/{task_id}")
async def get_schedule(task_id: str):
    sched = _scheduler.get_task(task_id)
    if not sched:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return sched


@app.delete("/api/schedules/{task_id}", status_code=204)
async def delete_schedule(task_id: str):
    _scheduler.remove_task(task_id)


@app.post("/api/schedules/{task_id}/pause", status_code=204)
async def pause_schedule(task_id: str):
    try:
        _scheduler.pause_task(task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/schedules/{task_id}/resume", status_code=204)
async def resume_schedule(task_id: str):
    try:
        _scheduler.resume_task(task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/schedules/{task_id}/trigger", status_code=202)
async def trigger_schedule(task_id: str):
    try:
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, _scheduler.trigger_now, task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"message": "已触发执行"}


# ─── 插件信息 ─────────────────────────────────────────────────────────────────

@app.get("/api/plugins")
async def list_available_plugins():
    from researchkit.plugins import PluginType, list_plugins
    return {
        "sources": list(list_plugins(PluginType.SOURCE).keys()),
        "processors": list(list_plugins(PluginType.PROCESSOR).keys()),
        "outputs": list(list_plugins(PluginType.OUTPUT).keys()),
    }


# ─── WebSocket 进度推送 ──────────────────────────────────────────────────────

@app.websocket("/ws/tasks/{task_id}")
async def task_progress_ws(websocket: WebSocket, task_id: str):
    await websocket.accept()
    _ws_connections.setdefault(task_id, []).append(websocket)
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        _ws_connections[task_id].remove(websocket)


async def _broadcast(task_id: str, event: dict):
    for ws in list(_ws_connections.get(task_id, [])):
        try:
            await ws.send_json(event)
        except Exception:
            pass


# ─── 内部：执行 Pipeline ─────────────────────────────────────────────────────

async def _run_pipeline(task_id: str, task: dict):
    loop = asyncio.get_event_loop()
    try:
        def run_sync():
            from researchkit.core.config import load_global_config
            from researchkit.core.models import ResearchContext, ResearchTask
            from researchkit.core.pipeline import Pipeline

            global_config = load_global_config()

            context = ResearchContext(
                topic=task["topic"],
                query=task.get("query", task["topic"]),
                keywords=task.get("keywords", []),
                time_range_days=task.get("time_range_days", 30),
            )
            rk_task = ResearchTask(
                name=task["name"],
                context=context,
                sources_config=task.get("sources_config", {}),
                pipeline_config=task.get("pipeline_config", []),
                output_config=task.get("output_config", {}),
            )

            progress_events = []

            def on_progress(stage, current, total, msg=""):
                event = {
                    "type": "progress",
                    "stage": stage,
                    "current": current,
                    "total": total,
                    "message": msg,
                }
                progress_events.append(event)
                # 异步广播不能直接 await，用 run_coroutine_threadsafe
                try:
                    asyncio.run_coroutine_threadsafe(
                        _broadcast(task_id, event), loop
                    ).result(timeout=2)
                except Exception:
                    pass

            pipeline = Pipeline(rk_task, global_config)
            report_md = pipeline.run(progress_callback=on_progress)

            # 保存报告路径
            from pathlib import Path
            output_dir = Path(rk_task.output_config.get("dir") or "~/Documents/research/").expanduser()
            safe_topic = "".join(c if c.isalnum() or c in "_ -" else "" for c in context.topic)[:30]
            date_str = datetime.now().strftime("%Y%m%d")
            report_path = str(output_dir / f"{date_str}_{safe_topic}.md")

            return report_path, len(rk_task.articles)

        report_path, article_count = await loop.run_in_executor(None, run_sync)
        store.update_task(task_id, {
            "status": TaskStatus.DONE,
            "report_path": report_path,
            "article_count": article_count,
            "finished_at": datetime.now().isoformat(),
        })
        await _broadcast(task_id, {
            "type": "done",
            "report_path": report_path,
            "article_count": article_count,
        })
    except Exception as e:
        logger.error(f"Pipeline 执行失败 [{task_id}]: {e}", exc_info=True)
        store.update_task(task_id, {
            "status": TaskStatus.FAILED,
            "error": str(e),
            "finished_at": datetime.now().isoformat(),
        })
        await _broadcast(task_id, {"type": "error", "message": str(e)})


# ─── 挂载前端静态文件（生产模式） ────────────────────────────────────────────
_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
