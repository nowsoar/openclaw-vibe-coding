"""小红书数据源（Playwright + Cookie 模式）"""
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from .base import BaseSource
from ..core.models import Article, ResearchContext

logger = logging.getLogger(__name__)

_AUTH_FILE = Path.home() / ".researchkit" / "xiaohongshu-auth.json"


class XiaohongshuSource(BaseSource):
    """小红书数据源适配器（通过 Cookie 登录，Playwright 渲染）"""

    def fetch(self, context: ResearchContext, since: datetime, limit: int = 50) -> list:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("playwright 未安装，请执行：pip install playwright && playwright install chromium")
            return []

        cookies = self._load_cookies()
        if not cookies:
            logger.warning("小红书 Cookie 未配置，请先执行：researchkit auth xiaohongshu")
            return []

        keywords = context.keywords or [context.topic]
        articles = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            ctx.add_cookies(cookies)
            page = ctx.new_page()

            for kw in keywords[:3]:  # 最多搜索 3 个关键词
                try:
                    fetched = self._search_keyword(page, kw, since, limit // len(keywords) + 10)
                    articles.extend(fetched)
                    if len(articles) >= limit:
                        break
                except Exception as e:
                    logger.warning(f"小红书搜索「{kw}」失败: {e}")

            browser.close()

        # 去重（URL 去重）
        seen = set()
        unique = []
        for a in articles:
            if a.url not in seen:
                seen.add(a.url)
                unique.append(a)

        return unique[:limit]

    def _search_keyword(self, page, keyword: str, since: datetime, limit: int) -> list:
        import time

        search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}&type=51"
        page.goto(search_url, timeout=30000)
        time.sleep(2)

        # 滚动加载更多
        for _ in range(3):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)

        # 抓取笔记卡片
        cards = page.query_selector_all("section.note-item")
        articles = []

        for card in cards[:limit]:
            try:
                article = self._parse_card(card, keyword)
                if article:
                    articles.append(article)
            except Exception as e:
                logger.debug(f"解析小红书卡片失败: {e}")

        return articles

    def _parse_card(self, card, keyword: str) -> Article | None:
        try:
            # 标题
            title_el = card.query_selector(".title span")
            title = title_el.inner_text().strip() if title_el else ""

            # 链接
            link_el = card.query_selector("a.cover")
            href = link_el.get_attribute("href") if link_el else ""
            if href and not href.startswith("http"):
                href = "https://www.xiaohongshu.com" + href

            # 作者
            author_el = card.query_selector(".author span.name")
            author = author_el.inner_text().strip() if author_el else ""

            # 封面图（无正文内容，后续通过 content_fetcher 补全）
            if not title or not href:
                return None

            return Article(
                title=title,
                url=href,
                source_type="xiaohongshu",
                source_name="小红书",
                content="",
                summary="",
                author=author,
                published_at=None,
            )
        except Exception:
            return None

    def _load_cookies(self) -> list:
        cookie_file = self.config.get("auth", str(_AUTH_FILE))
        path = Path(cookie_file).expanduser()
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("cookies", [])
        except Exception as e:
            logger.warning(f"读取小红书 Cookie 失败: {e}")
            return []

    def fetch_content(self, article: Article) -> str:
        """通过 Playwright 抓取笔记正文"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return ""

        cookies = self._load_cookies()
        if not cookies:
            return ""

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context()
                ctx.add_cookies(cookies)
                page = ctx.new_page()
                page.goto(article.url, timeout=20000)
                import time
                time.sleep(2)

                # 抓取正文
                content_el = page.query_selector("#detail-desc")
                content = content_el.inner_text().strip() if content_el else ""
                browser.close()
                return content
        except Exception as e:
            logger.debug(f"抓取小红书正文失败 {article.url}: {e}")
            return ""

    def health_check(self) -> tuple:
        cookie_file = self.config.get("auth", str(_AUTH_FILE))
        path = Path(cookie_file).expanduser()
        if not path.exists():
            return False, f"Cookie 文件不存在：{path}"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            cookies = data.get("cookies", [])
            if not cookies:
                return False, "Cookie 为空，请重新登录"
            # 检查过期
            saved_at = data.get("saved_at")
            if saved_at:
                saved_dt = datetime.fromisoformat(saved_at)
                age_days = (datetime.now() - saved_dt).days
                if age_days > 7:
                    return False, f"Cookie 已 {age_days} 天未更新，建议重新登录"
            return True, f"已配置 {len(cookies)} 个 Cookie 项"
        except Exception as e:
            return False, f"Cookie 读取异常: {e}"
