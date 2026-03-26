"""Markdown 报告输出"""
import logging
from datetime import datetime
from pathlib import Path
import yaml
from .base import BaseOutput
from ..core.models import Article, ResearchContext

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

DEFAULT_SYNTHESIS_PROMPT = """你是一位专业的行业分析师。
基于以下 {article_count} 篇整理好的资料，撰写关于"{topic}"的分析报告。
要求：结构清晰、数据翔实、有来源引用、中文表达专业易读。

资料摘要：
{articles_summary}"""


class MarkdownOutput(BaseOutput):
    """生成 Markdown 格式的调研报告"""

    def render(
        self,
        articles: list,
        context: ResearchContext,
        template_name: str,
        output_config: dict,
    ) -> str:
        template = self._load_template(template_name)
        global_config = getattr(self, "_global_config", None)

        # 构建文章摘要列表
        articles_summary = self._build_articles_summary(articles, output_config)

        # AI 合成完整报告
        if global_config:
            report_md = self._ai_synthesize(
                template, context, articles, articles_summary, global_config
            )
        else:
            # 没有 AI 时的降级处理：直接拼文章摘要
            report_md = self._fallback_report(context, articles, articles_summary)

        # 追加来源列表
        if output_config.get("include_source_list", True):
            report_md += self._source_list(articles)

        # 保存文件
        self._save(report_md, context, output_config)
        return report_md

    def _load_template(self, name: str) -> dict:
        path = _TEMPLATES_DIR / f"{name}.yaml"
        if not path.exists():
            logger.warning(f"模板 {name} 不存在，使用默认模板")
            return {"sections": [], "synthesis_prompt": DEFAULT_SYNTHESIS_PROMPT}
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _build_articles_summary(self, articles: list, output_config: dict) -> str:
        max_articles = output_config.get("max_articles_in_report", 30)
        lines = []
        for i, a in enumerate(articles[:max_articles], 1):
            pub = a.published_at.strftime("%Y-%m-%d") if a.published_at else "未知日期"
            lines.append(
                f"[{i}] {a.title}\n"
                f"    来源：{a.source_name}（{pub}）\n"
                f"    摘要：{a.summary or a.content[:200]}\n"
                f"    链接：{a.url}\n"
            )
        return "\n".join(lines)

    def _ai_synthesize(self, template, context, articles, articles_summary, global_config) -> str:
        try:
            from openai import OpenAI
            ai_cfg = global_config.ai
            client = OpenAI(api_key=ai_cfg.api_key, base_url=ai_cfg.base_url)
            model = ai_cfg.model_for("synthesize")

            synthesis_prompt_tpl = template.get("synthesis_prompt", DEFAULT_SYNTHESIS_PROMPT)
            synthesis_prompt = synthesis_prompt_tpl.format(
                topic=context.topic,
                article_count=len(articles),
                articles_summary=articles_summary,
            )
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": synthesis_prompt}],
                temperature=0.7,
                max_tokens=4000,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"AI 报告合成失败: {e}")
            return self._fallback_report(context, articles, articles_summary)

    def _fallback_report(self, context, articles, articles_summary) -> str:
        now = datetime.now().strftime("%Y年%m月%d日")
        return (
            f"# {context.topic}\n\n"
            f"> 生成时间：{now} | 共 {len(articles)} 篇来源\n\n"
            f"## 内容概览\n\n"
            f"{articles_summary}\n"
        )

    def _source_list(self, articles: list) -> str:
        lines = ["\n\n---\n\n## 参考来源\n"]
        for i, a in enumerate(articles, 1):
            pub = a.published_at.strftime("%Y-%m-%d") if a.published_at else ""
            lines.append(f"{i}. [{a.title}]({a.url}) — {a.source_name} {pub}")
        return "\n".join(lines)

    def _save(self, content: str, context: ResearchContext, output_config: dict):
        output_dir = Path(
            output_config.get("dir") or "~/Documents/research/"
        ).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)

        safe_topic = "".join(c if c.isalnum() or c in "_ -" else "" for c in context.topic)[:30]
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"{date_str}_{safe_topic}.md"
        path = output_dir / filename

        path.write_text(content, encoding="utf-8")
        logger.info(f"报告已保存：{path}")
