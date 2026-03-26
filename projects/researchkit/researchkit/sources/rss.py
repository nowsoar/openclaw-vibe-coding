"""RSS / Atom 数据源"""
import hashlib
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from .base import BaseSource
from ..core.models import Article, ResearchContext

logger = logging.getLogger(__name__)


class RSSSource(BaseSource):
    """RSS / Atom 订阅源适配器"""

    def fetch(self, context: ResearchContext, since: datetime, limit: int = 50) -> list:
        try:
            import feedparser
        except ImportError:
            logger.error("feedparser 未安装，请执行：pip install feedparser")
            return []

        feeds = self.config.get("feeds", [])
        articles = []

        for feed_cfg in feeds:
            feed_name = feed_cfg.get("name", "RSS")
            feed_url = feed_cfg.get("url", "")
            if not feed_url:
                continue

            try:
                parsed = feedparser.parse(feed_url)
                for entry in parsed.entries[:limit]:
                    pub_dt = self._parse_date(entry)
                    if pub_dt and since and pub_dt < since:
                        continue

                    article = Article(
                        title=entry.get("title", "").strip(),
                        url=entry.get("link", ""),
                        source_type="rss",
                        source_name=feed_name,
                        content=self._get_content(entry),
                        summary=entry.get("summary", "")[:500],
                        author=entry.get("author", ""),
                        published_at=pub_dt,
                    )
                    if article.title and article.url:
                        articles.append(article)
            except Exception as e:
                logger.warning(f"抓取 RSS {feed_name} 失败: {e}")

        return articles[:limit]

    def _parse_date(self, entry) -> datetime | None:
        for field in ("published", "updated"):
            val = entry.get(field)
            if val:
                try:
                    return parsedate_to_datetime(val)
                except Exception:
                    pass
        return None

    def _get_content(self, entry) -> str:
        content = entry.get("content")
        if content and isinstance(content, list):
            return content[0].get("value", "")
        return entry.get("summary", "")

    def health_check(self) -> tuple:
        feeds = self.config.get("feeds", [])
        if not feeds:
            return False, "未配置任何 RSS 订阅源"
        return True, f"已配置 {len(feeds)} 个订阅源"
