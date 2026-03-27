"""JSON 文件存储（Phase 3 临时方案，Phase 4 将迁移至 SQLite）"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .schemas import TaskCreate, TaskStatus

_STORE_FILE = Path.home() / ".researchkit" / "tasks.json"


class TaskStore:
    """线程安全的 JSON 文件任务存储"""

    def __init__(self, store_file: Path = _STORE_FILE):
        self._file = store_file
        self._lock = threading.Lock()
        self._file.parent.mkdir(parents=True, exist_ok=True)
        if not self._file.exists():
            self._write({})

    def _read(self) -> dict[str, dict]:
        try:
            return json.loads(self._file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write(self, data: dict):
        self._file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_tasks(self) -> list[dict]:
        with self._lock:
            data = self._read()
        tasks = list(data.values())
        tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
        return tasks

    def get_task(self, task_id: str) -> Optional[dict]:
        with self._lock:
            return self._read().get(task_id)

    def create_task(self, body: TaskCreate) -> dict:
        task_id = str(uuid.uuid4())
        task = {
            "id": task_id,
            "name": body.name,
            "topic": body.topic,
            "query": body.query,
            "keywords": body.keywords,
            "time_range_days": body.time_range_days,
            "sources_config": body.sources_config,
            "pipeline_config": body.pipeline_config,
            "output_config": body.output_config,
            "status": TaskStatus.PENDING,
            "article_count": 0,
            "report_path": None,
            "error": None,
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "finished_at": None,
        }
        with self._lock:
            data = self._read()
            data[task_id] = task
            self._write(data)
        return task

    def update_task(self, task_id: str, updates: dict[str, Any]) -> Optional[dict]:
        with self._lock:
            data = self._read()
            if task_id not in data:
                return None
            data[task_id].update(updates)
            self._write(data)
            return data[task_id]

    def delete_task(self, task_id: str) -> bool:
        with self._lock:
            data = self._read()
            if task_id not in data:
                return False
            del data[task_id]
            self._write(data)
            return True
