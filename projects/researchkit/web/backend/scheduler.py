"""定时任务调度器 (APScheduler)"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_SCHEDULE_FILE = Path.home() / ".researchkit" / "schedules.json"


class ResearchScheduler:
    """
    基于 APScheduler 的调研任务定时调度器。

    调度配置存储在 `~/.researchkit/schedules.json`，进程重启后自动恢复。

    用法示例::

        scheduler = ResearchScheduler()
        scheduler.start()
        scheduler.add_task(
            task_id="my_task",
            task_config={"name": "每日AI资讯", "topic": "AI工具"},
            cron_expr="0 8 * * *",   # 每天早上8点
        )
    """

    def __init__(self, run_callback: Optional[Callable] = None):
        """
        :param run_callback: 调度触发时的回调 fn(task_id, task_config)
        """
        self._scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        self._run_callback = run_callback or self._default_run
        self._lock = threading.Lock()
        _SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)

    def start(self):
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("ResearchScheduler 已启动")
            self._restore_schedules()

    def shutdown(self, wait: bool = False):
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("ResearchScheduler 已停止")

    def add_task(
        self,
        task_id: str,
        task_config: dict,
        cron_expr: str,
        *,
        incremental: bool = False,
        notification_config: Optional[dict] = None,
    ) -> dict:
        """添加定时调研任务。

        :param cron_expr: 标准五字段 cron 表达式，如 "0 8 * * *"
        :param incremental: True 则每次追加，而不是全量重跑
        :param notification_config: 完成后通知配置
        """
        self.remove_task(task_id)  # 先删除旧任务

        trigger = self._parse_cron(cron_expr)
        schedule = {
            "task_id": task_id,
            "task_config": task_config,
            "cron_expr": cron_expr,
            "incremental": incremental,
            "notification_config": notification_config or {},
            "created_at": datetime.now().isoformat(),
            "last_run": None,
            "next_run": None,
        }

        self._scheduler.add_job(
            func=self._trigger_run,
            trigger=trigger,
            id=task_id,
            args=[task_id, task_config, incremental, notification_config or {}],
            replace_existing=True,
        )

        # 更新 next_run
        job = self._scheduler.get_job(task_id)
        if job and job.next_run_time:
            schedule["next_run"] = job.next_run_time.isoformat()

        self._save_schedule(task_id, schedule)
        logger.info(f"已添加定时调研：{task_id} cron={cron_expr}")
        return schedule

    def remove_task(self, task_id: str) -> bool:
        try:
            self._scheduler.remove_job(task_id)
        except Exception:
            pass
        return self._delete_schedule(task_id)

    def list_tasks(self) -> list[dict]:
        schedules = self._load_schedules()
        result = []
        for sid, sched in schedules.items():
            job = self._scheduler.get_job(sid)
            sched = dict(sched)
            sched["next_run"] = job.next_run_time.isoformat() if job and job.next_run_time else None
            sched["running"] = self._scheduler.running
            result.append(sched)
        return result

    def get_task(self, task_id: str) -> Optional[dict]:
        schedules = self._load_schedules()
        return schedules.get(task_id)

    def pause_task(self, task_id: str):
        try:
            self._scheduler.pause_job(task_id)
        except Exception as e:
            raise ValueError(f"暂停失败: {e}") from e

    def resume_task(self, task_id: str):
        try:
            self._scheduler.resume_job(task_id)
        except Exception as e:
            raise ValueError(f"恢复失败: {e}") from e

    def trigger_now(self, task_id: str):
        """立即触发一次执行"""
        schedule = self.get_task(task_id)
        if not schedule:
            raise ValueError(f"未找到定时任务: {task_id}")
        self._trigger_run(
            task_id,
            schedule["task_config"],
            schedule.get("incremental", False),
            schedule.get("notification_config", {}),
        )

    # ─── 内部 ────────────────────────────────────────────────────────────────

    def _trigger_run(
        self,
        task_id: str,
        task_config: dict,
        incremental: bool,
        notification_config: dict,
    ):
        logger.info(f"定时调研触发：{task_id} incremental={incremental}")
        self._update_schedule_field(task_id, "last_run", datetime.now().isoformat())

        try:
            report_md = self._run_callback(task_id, task_config, incremental)

            # 通知
            if notification_config:
                try:
                    from .notifications import NotificationService
                    svc = NotificationService(notification_config)
                    svc.send(
                        title=f"调研完成：{task_config.get('name', task_id)}",
                        body=f"定时调研已完成，点击查看报告。",
                        report_md=report_md or "",
                    )
                except Exception as e:
                    logger.warning(f"通知发送失败: {e}")
        except Exception as e:
            logger.error(f"定时调研执行失败 [{task_id}]: {e}", exc_info=True)
            self._update_schedule_field(task_id, "last_error", str(e))

    def _default_run(self, task_id: str, task_config: dict, incremental: bool) -> str:
        """默认执行器（调用 Pipeline）"""
        from researchkit.core.config import load_global_config
        from researchkit.core.models import ResearchContext, ResearchTask
        from researchkit.core.pipeline import Pipeline

        global_config = load_global_config()
        context = ResearchContext(
            topic=task_config.get("topic", ""),
            query=task_config.get("query", ""),
            keywords=task_config.get("keywords", []),
            time_range_days=task_config.get("time_range_days", 30),
        )
        task = ResearchTask(
            name=task_config.get("name", task_id),
            context=context,
            sources_config=task_config.get("sources_config", {}),
            pipeline_config=task_config.get("pipeline_config", []),
            output_config=task_config.get("output_config", {}),
        )
        pipeline = Pipeline(task, global_config)
        return pipeline.run()

    @staticmethod
    def _parse_cron(expr: str) -> CronTrigger:
        parts = expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"无效的 cron 表达式（需要5个字段）: {expr}")
        minute, hour, day, month, day_of_week = parts
        return CronTrigger(
            minute=minute, hour=hour, day=day,
            month=month, day_of_week=day_of_week,
        )

    def _load_schedules(self) -> dict:
        if not _SCHEDULE_FILE.exists():
            return {}
        try:
            return json.loads(_SCHEDULE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_schedule(self, task_id: str, schedule: dict):
        with self._lock:
            schedules = self._load_schedules()
            schedules[task_id] = schedule
            _SCHEDULE_FILE.write_text(json.dumps(schedules, ensure_ascii=False, indent=2), encoding="utf-8")

    def _delete_schedule(self, task_id: str) -> bool:
        with self._lock:
            schedules = self._load_schedules()
            if task_id not in schedules:
                return False
            del schedules[task_id]
            _SCHEDULE_FILE.write_text(json.dumps(schedules, ensure_ascii=False, indent=2), encoding="utf-8")
            return True

    def _update_schedule_field(self, task_id: str, field: str, value: Any):
        with self._lock:
            schedules = self._load_schedules()
            if task_id in schedules:
                schedules[task_id][field] = value
                _SCHEDULE_FILE.write_text(json.dumps(schedules, ensure_ascii=False, indent=2), encoding="utf-8")

    def _restore_schedules(self):
        """进程重启后恢复定时任务"""
        schedules = self._load_schedules()
        for task_id, sched in schedules.items():
            try:
                self.add_task(
                    task_id=task_id,
                    task_config=sched["task_config"],
                    cron_expr=sched["cron_expr"],
                    incremental=sched.get("incremental", False),
                    notification_config=sched.get("notification_config"),
                )
                logger.info(f"已恢复定时任务：{task_id}")
            except Exception as e:
                logger.warning(f"恢复定时任务失败 [{task_id}]: {e}")


# 全局调度器实例（供 FastAPI lifespan 使用）
scheduler = ResearchScheduler()
