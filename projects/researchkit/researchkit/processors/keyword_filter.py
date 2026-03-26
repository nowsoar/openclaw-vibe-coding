"""关键词过滤处理器"""
import logging
from .base import BaseProcessor
from ..core.models import Article, ResearchContext

logger = logging.getLogger(__name__)


class KeywordFilter(BaseProcessor):
    """
    基于关键词过滤文章。
    config:
      keywords: [关键词1, 关键词2]   # 过滤关键词（空=使用 context.keywords）
      mode: any                       # any=含任意一个 / all=全包含
      weight_title: 2.0               # 标题命中视为更强信号（any 模式下）
    """

    def process(self, articles: list, context: ResearchContext) -> list:
        keywords = self.config.get("keywords") or context.keywords
        mode = self.config.get("mode", "any").lower()

        if not keywords:
            return articles  # 没有关键词就不过滤

        keywords_lower = [k.lower() for k in keywords]
        result = []

        for article in articles:
            text = f"{article.title} {article.title} {article.summary} {article.content}".lower()
            # 标题额外计权（通过重复出现提高命中率）

            if mode == "all":
                if all(kw in text for kw in keywords_lower):
                    result.append(article)
            else:  # any
                if any(kw in text for kw in keywords_lower):
                    result.append(article)

        logger.info(f"关键词过滤：{len(articles)} → {len(result)} 篇（mode={mode}）")
        return result
