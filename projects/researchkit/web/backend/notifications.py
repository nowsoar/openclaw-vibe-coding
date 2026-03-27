"""通知服务（飞书 Webhook / 邮件 / 通用 Webhook）"""
from __future__ import annotations

import logging
import smtplib
import urllib.request
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger(__name__)


class NotificationService:
    """
    统一通知服务，根据配置发送飞书/邮件/Webhook 通知。

    配置示例::

        {
            "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
            "email": {
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "username": "user@example.com",
                "password": "xxx",
                "to": ["team@example.com"]
            },
            "webhook": "https://hooks.example.com/notify"
        }
    """

    def __init__(self, config: dict):
        self._config = config or {}

    def send(self, title: str, body: str, report_md: str = "") -> None:
        """发送通知到所有已配置的渠道。"""
        errors: list[str] = []

        if self._config.get("feishu_webhook"):
            try:
                self._send_feishu(title, body, report_md)
            except Exception as e:
                logger.warning(f"飞书通知发送失败: {e}")
                errors.append(f"feishu: {e}")

        if self._config.get("email"):
            try:
                self._send_email(title, body, report_md)
            except Exception as e:
                logger.warning(f"邮件通知发送失败: {e}")
                errors.append(f"email: {e}")

        if self._config.get("webhook"):
            try:
                self._send_webhook(title, body, report_md)
            except Exception as e:
                logger.warning(f"Webhook 通知发送失败: {e}")
                errors.append(f"webhook: {e}")

        if errors:
            logger.warning(f"部分通知渠道失败: {errors}")

    # ─── 内部实现 ────────────────────────────────────────────────────────────

    def _send_feishu(self, title: str, body: str, report_md: str) -> None:
        """发送飞书机器人 Webhook 消息（富文本卡片）。"""
        url = self._config["feishu_webhook"]
        preview = report_md[:300] if report_md else body
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": title}},
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": preview},
                    }
                ],
            },
        }
        self._http_post(url, payload)

    def _send_email(self, title: str, body: str, report_md: str) -> None:
        """发送 SMTP 邮件。"""
        cfg = self._config["email"]
        msg = MIMEMultipart("alternative")
        msg["Subject"] = title
        msg["From"] = cfg["username"]
        recipients = cfg.get("to", [])
        msg["To"] = ", ".join(recipients)

        text_content = f"{body}\n\n{report_md}" if report_md else body
        msg.attach(MIMEText(text_content, "plain", "utf-8"))

        with smtplib.SMTP(cfg["smtp_host"], int(cfg.get("smtp_port", 587))) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(cfg["username"], cfg["password"])
            smtp.sendmail(cfg["username"], recipients, msg.as_string())

    def _send_webhook(self, title: str, body: str, report_md: str) -> None:
        """发送通用 Webhook（POST JSON）。"""
        url = self._config["webhook"]
        payload = {"title": title, "body": body, "report_preview": report_md[:500]}
        self._http_post(url, payload)

    @staticmethod
    def _http_post(url: str, payload: Any) -> None:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status}")
