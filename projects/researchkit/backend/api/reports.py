"""报告查看 API"""
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import ResearchTask

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("")
def list_reports(session: SessionDep):
    """列出所有已生成报告"""
    tasks = session.exec(
        select(ResearchTask)
        .where(ResearchTask.status == "done")
        .where(ResearchTask.report_path.isnot(None))
        .order_by(ResearchTask.updated_at.desc())
    ).all()
    return [
        {
            "task_id": t.id,
            "task_name": t.name,
            "topic": t.topic,
            "report_path": t.report_path,
            "article_count": t.article_count,
            "created_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in tasks
    ]


@router.get("/{task_id}")
def get_report(task_id: int, session: SessionDep):
    """获取指定任务的报告内容"""
    task = session.get(ResearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not task.report_path:
        raise HTTPException(status_code=404, detail="该任务尚无报告")

    path = Path(task.report_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="报告文件已被删除或移动")

    return {
        "task_id": task.id,
        "task_name": task.name,
        "topic": task.topic,
        "content": path.read_text(encoding="utf-8"),
        "path": str(path),
        "article_count": task.article_count,
    }


@router.delete("/{task_id}")
def delete_report(task_id: int, session: SessionDep):
    """删除报告文件（保留任务记录）"""
    task = session.get(ResearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.report_path:
        p = Path(task.report_path)
        if p.exists():
            p.unlink()
        task.report_path = None
        session.add(task)
        session.commit()
    return {"ok": True}
