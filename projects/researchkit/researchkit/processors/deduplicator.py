"""去重处理器"""
import logging
from .base import BaseProcessor
from ..core.models import Article, ResearchContext

logger = logging.getLogger(__name__)


class Deduplicator(BaseProcessor):
    """
    基于 URL 去重（简单版）。
    config:
      keep: first   # first=保留第一个 / last=保留最后一个
    """

    def process(self, articles: list, context: ResearchContext) -> list:
        keep = self.config.get("keep", "first")
        seen_urls = set()
        seen_ids = set()
        result = []

        items = articles if keep == "first" else list(reversed(articles))

        for article in items:
            key = article.url.strip().rstrip("/")
            if key in seen_urls or article.id in seen_ids:
                continue
            seen_urls.add(key)
            seen_ids.add(article.id)
            result.append(article)

        if keep != "first":
            result = list(reversed(result))

        logger.info(f"去重：{len(articles)} → {len(result)} 篇")
        return result
