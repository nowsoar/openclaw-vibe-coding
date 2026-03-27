"""任务 CRUD API"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session, select

from ..db import get_session
from ..models import ResearchTask, ResearchTaskCreate, ResearchTaskRead, ResearchTaskUpdate
from ..ws.progress import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["tasks"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[ResearchTaskRead])
def list_tasks(session: SessionDep, status: Optional[str] = None):
    stmt = select(ResearchTask)
    if status:
        stmt = stmt.where(ResearchTask.status == status)
    return session.exec(stmt.order_by(ResearchTask.created_at.desc())).all()


@router.post("", response_model=ResearchTaskRead, status_code=201)
def create_task(task_in: ResearchTaskCreate, session: SessionDep):
    task = ResearchTask(**task_in.model_dump())
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.get("/{task_id}", response_model=ResearchTaskRead)
def get_task(task_id: int, session: SessionDep):
    task = session.get(ResearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.patch("/{task_id}", response_model=ResearchTaskRead)
def update_task(task_id: int, task_in: ResearchTaskUpdate, session: SessionDep):
    task = session.get(ResearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    for field, value in task_in.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: int, session: SessionDep):
    task = session.get(ResearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    session.delete(task)
    session.commit()


@router.post("/{task_id}/run", response_model=ResearchTaskRead)
def run_task(task_id: int, background_tasks: BackgroundTasks, session: SessionDep):
    task = session.get(ResearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status == "running":
        raise HTTPException(status_code=409, detail="任务正在运行中")

    task.status = "running"
    task.updated_at = datetime.utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)

    background_tasks.add_task(_execute_task, task_id)
    return task


@router.get("/{task_id}/report")
def get_report(task_id: int, session: SessionDep):
    task = session.get(ResearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not task.report_path:
        raise HTTPException(status_code=404, detail="报告尚未生成")
    from pathlib import Path
    path = Path(task.report_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="报告文件不存在")
    return {"content": path.read_text(encoding="utf-8"), "path": str(path)}


# ──────────────────────────────────────────────────────────────────────────────
# Background task execution
# ──────────────────────────────────────────────────────────────────────────────

def _execute_task(task_id: int):
    """在线程中运行 Pipeline，通过 asyncio 广播进度"""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_async_execute(task_id))
    finally:
        loop.close()


async def _async_execute(task_id: int):
    from ..db import engine
    from sqlmodel import Session as _Session

    with _Session(engine) as session:
        task = session.get(ResearchTask, task_id)
        if not task:
            return

        try:
            report_md, article_count, report_path = await _run_pipeline(task)

            task.status = "done"
            task.article_count = article_count
            task.report_path = str(report_path) if report_path else ""
            task.error = None
            task.updated_at = datetime.utcnow()
            session.add(task)
            session.commit()

            await manager.send_done(task_id, article_count, str(report_path) if report_path else "")

        except Exception as exc:
            logger.exception(f"任务 {task_id} 执行失败")
            task.status = "failed"
            task.error = str(exc)
            task.updated_at = datetime.utcnow()
            session.add(task)
            session.commit()
            await manager.send_error(task_id, str(exc))


async def _run_pipeline(task: ResearchTask):
    """构建并运行 Pipeline，返回 (report_md, article_count, report_path)"""
    import asyncio
    from pathlib import Path

    from researchkit.core.config import load_global_config, GlobalConfig, AIConfig
    from researchkit.core.models import ResearchContext, ResearchTask as CoreTask, TaskStatus
    from researchkit.core.pipeline import Pipeline

    # 构建 CoreTask
    keywords = json.loads(task.keywords) if task.keywords else []
    context = ResearchContext(
        topic=task.topic,
        query=task.query,
        keywords=keywords,
        time_range_days=task.time_range_days,
    )
    sources_config = json.loads(task.sources_config)
    pipeline_config = json.loads(task.pipeline_config)
    output_config = json.loads(task.output_config)
    output_config.setdefault("template", task.template)

    core_task = CoreTask(
        name=task.name,
        context=context,
        sources_config=sources_config,
        pipeline_config=pipeline_config,
        output_config=output_config,
    )

    # 加载全局配置
    try:
        global_config = load_global_config()
    except Exception:
        global_config = GlobalConfig(ai=AIConfig())

    # 进度回调
    async def progress_cb(stage, current, total, msg=""):
        await manager.send_progress(task.id, stage, current, total, msg)

    def sync_progress(stage, current, total, msg=""):
        asyncio.get_event_loop().call_soon_threadsafe(
            asyncio.ensure_future,
            manager.send_progress(task.id, stage, current, total, msg)
        )

    pipeline = Pipeline(task=core_task, global_config=global_config)
    loop = asyncio.get_event_loop()
    report_md = await loop.run_in_executor(None, lambda: pipeline.run(sync_progress))

    # 查找报告文件路径
    from pathlib import Path as _Path
    output_dir = _Path(output_config.get("dir", "~/Documents/research/")).expanduser()
    report_files = sorted(output_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    report_path = report_files[0] if report_files else None

    return report_md, len(core_task.articles), report_path
