"""飞书文档输出"""
import json
import logging
from datetime import datetime
from pathlib import Path

import requests

from .base import BaseOutput
from ..core.models import Article, ResearchContext

logger = logging.getLogger(__name__)


class FeishuOutput(BaseOutput):
    """将报告发布为飞书云文档"""

    def render(
        self,
        articles: list,
        context: ResearchContext,
        template_name: str,
        output_config: dict,
    ) -> str:
        # 先生成 Markdown 内容
        from .markdown import MarkdownOutput
        md_output = MarkdownOutput(config=self.config)
        md_output._global_config = getattr(self, "_global_config", None)
        report_md = md_output.render(articles, context, template_name, output_config)

        # 发布到飞书
        feishu_cfg = output_config.get("feishu", self.config)
        app_id = feishu_cfg.get("app_id") or ""
        app_secret = feishu_cfg.get("app_secret") or ""
        folder_token = feishu_cfg.get("folder_token", "")

        if not app_id or not app_secret:
            logger.warning("飞书 app_id / app_secret 未配置，跳过飞书发布")
            return report_md

        try:
            token = self._get_access_token(app_id, app_secret)
            doc_url = self._create_doc(token, context.topic, report_md, folder_token)
            logger.info(f"报告已发布到飞书：{doc_url}")
        except Exception as e:
            logger.error(f"飞书文档发布失败: {e}")

        return report_md

    def _get_access_token(self, app_id: str, app_secret: str) -> str:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取飞书 Token 失败: {data.get('msg')}")
        return data["tenant_access_token"]

    def _create_doc(self, token: str, title: str, content: str, folder_token: str) -> str:
        """创建飞书文档（使用 DocX API）"""
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        date_str = datetime.now().strftime("%Y-%m-%d")
        doc_title = f"{title} — {date_str}"

        # 将 Markdown 转换为飞书 DocX Block 格式
        blocks = self._md_to_feishu_blocks(content)

        body: dict = {
            "title": doc_title,
            "folder_token": folder_token,
            "content": {"blocks": blocks},
        }

        resp = requests.post(
            "https://open.feishu.cn/open-apis/docx/v1/documents",
            headers=headers,
            json=body,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"创建飞书文档失败: {data.get('msg')}")

        doc_token = data["data"]["document"]["document_id"]
        return f"https://feishu.cn/docx/{doc_token}"

    def _md_to_feishu_blocks(self, md: str) -> list:
        """将 Markdown 文本简单转为飞书 Block 列表"""
        blocks = []
        for line in md.split("\n"):
            line = line.rstrip()
            if line.startswith("# "):
                blocks.append(self._heading_block(line[2:], 1))
            elif line.startswith("## "):
                blocks.append(self._heading_block(line[3:], 2))
            elif line.startswith("### "):
                blocks.append(self._heading_block(line[4:], 3))
            else:
                blocks.append(self._text_block(line))
        return blocks

    def _heading_block(self, text: str, level: int) -> dict:
        block_type = {1: "heading1", 2: "heading2", 3: "heading3"}.get(level, "heading2")
        return {
            "block_type": block_type,
            block_type: {
                "elements": [{"text_run": {"content": text}}],
            },
        }

    def _text_block(self, text: str) -> dict:
        return {
            "block_type": "paragraph",
            "paragraph": {
                "elements": [{"text_run": {"content": text}}],
            },
        }
