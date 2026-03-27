"""WebSocket 实时进度推送"""
import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """管理所有 WebSocket 连接，按 task_id 分组"""

    def __init__(self):
        self._connections: dict[int, list[WebSocket]] = defaultdict(list)

    async def connect(self, task_id: int, ws: WebSocket):
        await ws.accept()
        self._connections[task_id].append(ws)
        logger.debug(f"WS connected: task={task_id}, total={len(self._connections[task_id])}")

    def disconnect(self, task_id: int, ws: WebSocket):
        conns = self._connections.get(task_id, [])
        if ws in conns:
            conns.remove(ws)

    async def broadcast(self, task_id: int, payload: dict[str, Any]):
        """向 task_id 的所有连接广播消息"""
        message = json.dumps(payload, ensure_ascii=False)
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(task_id, [])):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(task_id, ws)

    async def send_progress(self, task_id: int, stage: str, current: int, total: int, msg: str = ""):
        await self.broadcast(task_id, {
            "type": "progress",
            "stage": stage,
            "current": current,
            "total": total,
            "message": msg,
        })

    async def send_done(self, task_id: int, article_count: int, report_path: str = ""):
        await self.broadcast(task_id, {
            "type": "done",
            "article_count": article_count,
            "report_path": report_path,
        })

    async def send_error(self, task_id: int, error: str):
        await self.broadcast(task_id, {
            "type": "error",
            "message": error,
        })


manager = ConnectionManager()
