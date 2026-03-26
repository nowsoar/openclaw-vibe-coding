"""AI 摘要处理器"""
import logging
from .base import BaseProcessor
from ..core.models import Article, ResearchContext

logger = logging.getLogger(__name__)

DEFAULT_PROMPT = """用中文总结以下文章的核心内容，不超过{max_words}字。
重点提炼：主要观点、关键数据、核心结论。
不要以"本文"或"文章"开头，直接给出内容。

文章：{content}"""


class AISummarizer(BaseProcessor):
    """
    使用 AI 为每篇文章生成摘要。
    config:
      max_words: 120
      prompt: null    # 自定义 prompt（支持 {max_words}/{title}/{content} 变量）
      model: null     # 可覆盖默认模型
      skip_if_has_summary: true  # 已有摘要的文章跳过
    """

    def process(self, articles: list, context: ResearchContext) -> list:
        try:
            from openai import OpenAI
        except ImportError:
            logger.error("openai 未安装，跳过摘要生成")
            return articles

        global_config = getattr(self, "_global_config", None)
        if not global_config:
            logger.warning("未获取到 global_config，跳过 AI 摘要")
            return articles

        ai_cfg = global_config.ai
        client = OpenAI(api_key=ai_cfg.api_key, base_url=ai_cfg.base_url)
        model = self.config.get("model") or ai_cfg.model_for("summarize")
        max_words = int(self.config.get("max_words", 120))
        prompt_tpl = self.config.get("prompt") or DEFAULT_PROMPT
        skip_if_has = self.config.get("skip_if_has_summary", True)

        for article in articles:
            if skip_if_has and article.summary:
                continue
            content = article.content or article.summary
            if not content:
                article.summary = article.title
                continue
            try:
                prompt = prompt_tpl.format(
                    max_words=max_words,
                    title=article.title,
                    content=content[:2000],
                )
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.5,
                    max_tokens=300,
                )
                article.summary = resp.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"生成摘要失败（{article.title[:30]}）: {e}")
                if not article.summary:
                    article.summary = article.title

        return articles
