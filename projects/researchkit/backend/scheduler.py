"""定时任务调度器（APScheduler）"""
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# 全局单例调度器
scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


def start():
    """启动调度器（在 FastAPI lifespan 中调用）"""
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler 已启动")


def shutdown():
    """关闭调度器"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler 已关闭")


def add_task_job(task_id: int, cron_expr: str):
    """为指定任务添加定时 cron 作业"""
    job_id = _job_id(task_id)
    # 先移除同 id 的旧作业（防止重复）
    remove_task_job(task_id)
    try:
        trigger = CronTrigger.from_crontab(cron_expr, timezone="Asia/Shanghai")
    except Exception as exc:
        raise ValueError(f"无效的 cron 表达式 '{cron_expr}': {exc}")

    scheduler.add_job(
        _trigger_task,
        trigger=trigger,
        id=job_id,
        args=[task_id],
        replace_existing=True,
        misfire_grace_time=60,
    )
    logger.info(f"已添加定时任务 job_id={job_id}, cron={cron_expr}")


def remove_task_job(task_id: int):
    """移除定时作业"""
    job_id = _job_id(task_id)
    try:
        scheduler.remove_job(job_id)
        logger.info(f"已移除定时任务 job_id={job_id}")
    except Exception:
        pass  # 不存在则忽略


def get_job_info(task_id: int) -> Optional[dict]:
    """获取作业下次触发时间等信息"""
    job = scheduler.get_job(_job_id(task_id))
    if not job:
        return None
    return {
        "job_id": job.id,
        "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
    }


def restore_all_jobs():
    """从数据库恢复所有定时任务（应用启动时调用）"""
    from .db import engine
    from sqlmodel import Session, select
    from .models import ResearchTask

    with Session(engine) as session:
        tasks = session.exec(
            select(ResearchTask).where(ResearchTask.schedule_cron.isnot(None))
        ).all()
        for task in tasks:
            try:
                add_task_job(task.id, task.schedule_cron)
            except Exception as exc:
                logger.warning(f"恢复定时任务 {task.id} 失败: {exc}")
    logger.info(f"已恢复 {len(tasks)} 个定时任务")


# ──────────────────────────────────────────────────────────────────────────────
# 内部
# ──────────────────────────────────────────────────────────────────────────────

def _job_id(task_id: int) -> str:
    return f"research_task_{task_id}"


async def _trigger_task(task_id: int):
    """定时触发：创建新的"执行副本"并运行"""
    from .db import engine
    from sqlmodel import Session
    from .models import ResearchTask
    from .api.tasks import _execute_task
    from datetime import datetime
    import asyncio

    with Session(engine) as session:
        task = session.get(ResearchTask, task_id)
        if not task:
            logger.warning(f"定时任务 {task_id} 对应的 ResearchTask 不存在，跳过")
            return
        if task.status == "running":
            logger.info(f"定时任务 {task_id} 上次运行尚未完成，跳过本次触发")
            return

        task.status = "running"
        task.updated_at = datetime.utcnow()
        session.add(task)
        session.commit()
        logger.info(f"定时任务 {task_id} 已触发")

    # 在线程中异步执行
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _execute_task, task_id)

    # 触发后通知
    from .notifier import notify_task_started
    await notify_task_started(task_id)
