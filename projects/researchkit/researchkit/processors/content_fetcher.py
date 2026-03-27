"""正文抓取处理器（补充文章 content 字段）"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .base import BaseProcessor
from ..core.models import Article, ResearchContext

logger = logging.getLogger(__name__)

# 站点特定选择器（优先级高于通用选择器）
_SITE_SELECTORS: dict[str, str] = {
    "zhihu.com": ".Post-RichTextContainer, .RichText",
    "csdn.net": "#article_content, .article_content",
    "jianshu.com": ".ouvJEz",
    "36kr.com": ".article-content, .common-content",
    "sspai.com": ".article-body",
    "juejin.cn": ".article-content",
    "infoq.cn": ".article-preview, article",
    "github.com": "#readme article, .markdown-body",
    "mp.weixin.qq.com": "#js_content",
    "medium.com": "article .pw-post-body-paragraph",
}

_GENERIC_SELECTORS = (
    "article",
    "main",
    ".content",
    ".post-content",
    ".article-body",
    ".entry-content",
    ".post-body",
    "#content",
    ".markdown-body",
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class ContentFetcherProcessor(BaseProcessor):
    """为 content 为空的文章抓取正文，支持重试和站点特定解析"""

    def process(self, articles: list[Article], context: ResearchContext) -> list[Article]:
        timeout = self.config.get("timeout", 12)
        max_workers = self.config.get("max_workers", 5)
        max_chars = self.config.get("max_chars", 8000)
        retries = self.config.get("retries", 3)
        custom_selector = self.config.get("content_selector", "")

        need_fetch = [a for a in articles if not (a.content or "").strip()]
        if not need_fetch:
            return articles

        logger.info(f"正文抓取：需要补充 {len(need_fetch)} 篇")

        def fetch_one(article: Article) -> tuple[str, str]:
            return article.id, _fetch_with_retry(
                article.url, timeout, retries, max_chars, custom_selector
            )

        id_to_content: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_one, a): a for a in need_fetch}
            for future in as_completed(futures):
                article_id, content = future.result()
                id_to_content[article_id] = content

        for article in articles:
            if article.id in id_to_content and id_to_content[article.id]:
                article.content = id_to_content[article.id]

        return articles


# ──────────────────────────────────────────────────────────────────────────────
# 模块级辅助函数（方便测试）
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_with_retry(
    url: str,
    timeout: int,
    retries: int,
    max_chars: int,
    custom_selector: str = "",
) -> str:
    """带指数退避重试的正文抓取"""
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=timeout, headers=_HEADERS)
            resp.raise_for_status()
            return _extract_content(resp.text, url, max_chars, custom_selector)
        except requests.exceptions.HTTPError as exc:
            # 4xx 客户端错误不重试
            if exc.response is not None and exc.response.status_code < 500:
                logger.debug(f"正文抓取 HTTP {exc.response.status_code} [{url[:60]}]，不重试")
                return ""
            last_exc = exc
        except Exception as exc:
            last_exc = exc

        if attempt < retries:
            wait = 2 ** (attempt - 1)  # 1s, 2s, 4s ...
            logger.debug(f"正文抓取第 {attempt} 次失败，{wait}s 后重试 [{url[:60]}]: {last_exc}")
            time.sleep(wait)

    logger.warning(f"正文抓取失败（{retries} 次重试）[{url[:60]}]: {last_exc}")
    return ""


def _extract_content(html: str, url: str, max_chars: int, custom_selector: str = "") -> str:
    """从 HTML 提取正文，优先使用站点特定选择器"""
    soup = BeautifulSoup(html, "html.parser")

    # 移除噪音标签
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "ads"]):
        tag.decompose()

    # 自定义选择器优先
    if custom_selector:
        for sel in custom_selector.split(","):
            el = soup.select_one(sel.strip())
            if el:
                return _clean_text(el.get_text(separator="\n", strip=True), max_chars)

    # 站点特定选择器
    for domain, selector in _SITE_SELECTORS.items():
        if domain in url:
            for sel in selector.split(","):
                el = soup.select_one(sel.strip())
                if el:
                    return _clean_text(el.get_text(separator="\n", strip=True), max_chars)

    # 通用选择器
    for sel in _GENERIC_SELECTORS:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(separator="\n", strip=True)
            if len(text) > 200:  # 太短说明不是正文
                return _clean_text(text, max_chars)

    # 兜底：body 全文
    body = soup.find("body")
    text = body.get_text(separator="\n", strip=True) if body else ""
    return _clean_text(text, max_chars)


def _clean_text(text: str, max_chars: int) -> str:
    """去除多余空行，截断超长内容"""
    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]
    cleaned = "\n".join(lines)
    return cleaned[:max_chars]
