"""正文抓取处理器（补充文章 content 字段）"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

from .base import BaseProcessor
from ..core.models import Article, ResearchContext

logger = logging.getLogger(__name__)


class ContentFetcherProcessor(BaseProcessor):
    """为 content 为空的文章抓取正文"""

    def process(self, articles: list[Article], context: ResearchContext) -> list[Article]:
        timeout = self.config.get("timeout", 10)
        max_workers = self.config.get("max_workers", 5)
        content_selector = self.config.get(
            "content_selector", "article, main, .content, .post-content, .article-body"
        )

        # 只处理没有正文的文章
        need_fetch = [a for a in articles if not a.content.strip()]
        if not need_fetch:
            return articles

        logger.info(f"正文抓取：需要补充 {len(need_fetch)} 篇")

        def fetch_one(article: Article) -> tuple[str, str]:
            try:
                resp = requests.get(
                    article.url,
                    timeout=timeout,
                    headers={"User-Agent": "Mozilla/5.0 ResearchKit/0.1"},
                )
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                for selector in content_selector.split(","):
                    el = soup.select_one(selector.strip())
                    if el:
                        return article.id, el.get_text(separator="\n", strip=True)
                body = soup.find("body")
                text = body.get_text(separator="\n", strip=True) if body else ""
                return article.id, text[:5000]  # 截断超长内容
            except Exception as e:
                logger.warning(f"正文抓取失败 [{article.url[:60]}]: {e}")
                return article.id, ""

        id_to_content = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_one, a): a for a in need_fetch}
            for future in as_completed(futures):
                article_id, content = future.result()
                id_to_content[article_id] = content

        # 回填 content
        for article in articles:
            if article.id in id_to_content:
                article.content = id_to_content[article.id]

        return articles
