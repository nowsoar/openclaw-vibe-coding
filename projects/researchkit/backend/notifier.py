"""飞书 / Webhook 通知推送"""
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# 从环境变量读取配置
FEISHU_WEBHOOK = os.getenv("RESEARCHKIT_FEISHU_WEBHOOK", "")
CUSTOM_WEBHOOK = os.getenv("RESEARCHKIT_WEBHOOK", "")


def send_feishu(webhook_url: str, title: str, content: str) -> bool:
    """发送飞书群机器人消息（卡片格式）"""
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": content},
                }
            ],
        },
    }
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code", 0) != 0 and data.get("StatusCode", 0) != 0:
            logger.warning(f"飞书推送异常: {data}")
            return False
        return True
    except Exception as exc:
        logger.error(f"飞书推送失败: {exc}")
        return False


def send_webhook(webhook_url: str, payload: dict) -> bool:
    """发送通用 Webhook（POST JSON）"""
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error(f"Webhook 推送失败: {exc}")
        return False


async def notify_task_done(task_id: int, topic: str, article_count: int, report_path: str = ""):
    """任务完成时发送通知"""
    title = f"✅ ResearchKit 调研完成：{topic}"
    content = (
        f"**任务 ID**：{task_id}\n"
        f"**主题**：{topic}\n"
        f"**文章数**：{article_count}\n"
        f"**报告**：{report_path or '未生成'}"
    )
    _dispatch(title, content, {"event": "task_done", "task_id": task_id,
                                "topic": topic, "article_count": article_count})


async def notify_task_failed(task_id: int, topic: str, error: str):
    """任务失败时发送通知"""
    title = f"❌ ResearchKit 任务失败：{topic}"
    content = f"**任务 ID**：{task_id}\n**错误**：{error}"
    _dispatch(title, content, {"event": "task_failed", "task_id": task_id,
                                "topic": topic, "error": error})


async def notify_task_started(task_id: int):
    """定时任务触发时发送通知"""
    title = "🚀 ResearchKit 定时调研已触发"
    content = f"**任务 ID**：{task_id}\n定时任务已开始执行，请稍后查看结果。"
    _dispatch(title, content, {"event": "task_started", "task_id": task_id})


def _dispatch(title: str, content: str, payload: dict):
    """根据配置选择通知渠道"""
    if FEISHU_WEBHOOK:
        send_feishu(FEISHU_WEBHOOK, title, content)
    if CUSTOM_WEBHOOK:
        send_webhook(CUSTOM_WEBHOOK, {"title": title, "content": content, **payload})
