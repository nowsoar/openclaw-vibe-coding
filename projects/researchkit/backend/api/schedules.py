"""定时调研 API"""
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import ResearchTask, ResearchTaskRead, User
from ..scheduler import add_task_job, remove_task_job, get_job_info
from .auth import get_current_user_optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/schedules", tags=["schedules"])
SessionDep = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[Optional[User], Depends(get_current_user_optional)]


@router.get("")
def list_scheduled_tasks(session: SessionDep, current_user: CurrentUser):
    """列出所有已配置定时调研的任务"""
    stmt = select(ResearchTask).where(ResearchTask.schedule_cron.isnot(None))
    if current_user:
        stmt = stmt.where(ResearchTask.user_id == current_user.id)
    tasks = session.exec(stmt).all()
    result = []
    for t in tasks:
        info = get_job_info(t.id)
        result.append({
            "task_id": t.id,
            "task_name": t.name,
            "topic": t.topic,
            "schedule_cron": t.schedule_cron,
            "status": t.status,
            "next_run": info["next_run"] if info else None,
        })
    return result


@router.put("/{task_id}")
def set_schedule(
    task_id: int,
    cron_expr: str,
    session: SessionDep,
    current_user: CurrentUser,
):
    """为任务设置或更新定时 cron 表达式"""
    task = session.get(ResearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if current_user and task.user_id is not None and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权修改此任务")

    try:
        add_task_job(task_id, cron_expr)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    task.schedule_cron = cron_expr
    session.add(task)
    session.commit()
    session.refresh(task)

    info = get_job_info(task_id)
    return {
        "task_id": task_id,
        "schedule_cron": cron_expr,
        "next_run": info["next_run"] if info else None,
    }


@router.delete("/{task_id}", status_code=204)
def remove_schedule(task_id: int, session: SessionDep, current_user: CurrentUser):
    """取消任务的定时调度"""
    task = session.get(ResearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if current_user and task.user_id is not None and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权修改此任务")

    remove_task_job(task_id)
    task.schedule_cron = None
    session.add(task)
    session.commit()


@router.get("/{task_id}")
def get_schedule(task_id: int, session: SessionDep):
    """查询任务的定时配置和下次执行时间"""
    task = session.get(ResearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    info = get_job_info(task_id)
    return {
        "task_id": task_id,
        "schedule_cron": task.schedule_cron,
        "next_run": info["next_run"] if info else None,
        "is_active": info is not None,
    }
