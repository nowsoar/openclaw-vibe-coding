"""网页抓取数据源"""
import logging
from datetime import datetime, timezone
from typing import Optional
from .base import BaseSource
from ..core.models import Article, ResearchContext

logger = logging.getLogger(__name__)


class WebSource(BaseSource):
    """指定网站抓取适配器，通过 CSS 选择器定位文章列表和正文"""

    def fetch(self, context: ResearchContext, since: datetime, limit: int = 50) -> list:
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("requests 或 beautifulsoup4 未安装")
            return []

        targets = self.config.get("targets", [])
        timeout = self.config.get("timeout", 10)
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        articles = []

        for target in targets:
            name = target.get("name", "")
            base_url = target.get("url", "")
            article_sel = target.get("article_selector", "a")
            content_sel = target.get("content_selector", "article, main, .content")
            max_per_target = target.get("max_articles", 20)

            if not base_url:
                continue

            try:
                resp = requests.get(base_url, headers=headers, timeout=timeout)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                links = []
                for el in soup.select(article_sel)[:max_per_target]:
                    href = el.get("href", "")
                    if href:
                        if href.startswith("/"):
                            from urllib.parse import urlparse
                            parsed = urlparse(base_url)
                            href = f"{parsed.scheme}://{parsed.netloc}{href}"
                        title = el.get_text(strip=True) or href
                        links.append((title, href))

                for title, url in links[:max_per_target]:
                    article = Article(
                        title=title,
                        url=url,
                        source_type="web",
                        source_name=name,
                    )
                    articles.append(article)
            except Exception as e:
                logger.warning(f"抓取网站 {name} 失败: {e}")

        return articles[:limit]

    def fetch_content(self, article: Article) -> str:
        """单独抓取文章正文"""
        if article.content:
            return article.content
        try:
            import requests
            from bs4 import BeautifulSoup

            resp = requests.get(
                article.url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            # 尝试提取正文
            for sel in ["article", "main", ".content", ".post-body", "body"]:
                el = soup.select_one(sel)
                if el:
                    text = el.get_text(separator="\n", strip=True)
                    if len(text) > 200:
                        return text[:3000]
        except Exception as e:
            logger.debug(f"抓取正文失败 {article.url}: {e}")
        return ""

    def health_check(self) -> tuple:
        targets = self.config.get("targets", [])
        if not targets:
            return False, "未配置任何目标网站"
        return True, f"已配置 {len(targets)} 个目标网站"
