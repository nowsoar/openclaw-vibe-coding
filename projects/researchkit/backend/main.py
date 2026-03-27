"""ResearchKit FastAPI 应用入口"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .api import tasks as tasks_router
from .api import sources as sources_router
from .api import reports as reports_router
from .api import auth as auth_router
from .api import schedules as schedules_router
from .ws.progress import manager
from . import scheduler as task_scheduler

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# 应用生命周期
# ──────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task_scheduler.start()
    task_scheduler.restore_all_jobs()
    logger.info("ResearchKit backend started, database initialized.")
    yield
    task_scheduler.shutdown()
    logger.info("ResearchKit backend shutting down.")


app = FastAPI(
    title="ResearchKit API",
    version="0.2.0",
    description="AI 驱动的自动化调研平台 REST API",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 路由注册 ──────────────────────────────────────────────────────────────────
app.include_router(auth_router.router, prefix="/api")
app.include_router(tasks_router.router, prefix="/api")
app.include_router(sources_router.router, prefix="/api")
app.include_router(reports_router.router, prefix="/api")
app.include_router(schedules_router.router, prefix="/api")


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws/tasks/{task_id}")
async def websocket_task_progress(task_id: int, websocket: WebSocket):
    await manager.connect(task_id, websocket)
    try:
        while True:
            # 接收 ping/pong，保持连接
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(task_id, websocket)


# ── 前端静态文件（生产模式）──────────────────────────────────────────────────
_DIST_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if _DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_DIST_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
