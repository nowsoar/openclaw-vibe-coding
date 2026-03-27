"""引用验证处理器 — 检查来源链接可访问性"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from .base import BaseProcessor
from ..core.models import Article, ResearchContext

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 8


class ReferenceValidator(BaseProcessor):
    """验证文章来源链接是否可访问，过滤失效链接"""

    def process(self, articles: list, context: ResearchContext) -> list:
        remove_invalid = self.config.get("remove_invalid", False)
        timeout = self.config.get("timeout", _DEFAULT_TIMEOUT)
        max_workers = self.config.get("max_workers", 10)

        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(self._check_url, a.url, timeout): a
                for a in articles
            }
            for future in as_completed(future_map):
                article = future_map[future]
                try:
                    accessible = future.result()
                except Exception:
                    accessible = True  # 检查失败时保留文章
                results[article.url] = accessible

        valid, invalid = [], []
        for a in articles:
            if results.get(a.url, True):
                valid.append(a)
            else:
                invalid.append(a)
                logger.debug(f"链接失效: {a.url}")

        if invalid:
            logger.info(f"引用验证：{len(invalid)} 篇链接失效，{len(valid)} 篇有效")

        if remove_invalid:
            return valid
        else:
            # 不过滤，只在日志里标记
            return articles

    def _check_url(self, url: str, timeout: int) -> bool:
        """返回 True 表示可访问，False 表示不可访问（HTTP 错误或网络异常）"""
        try:
            resp = requests.head(
                url,
                timeout=timeout,
                allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 ResearchKit/1.0"},
            )
            if resp.status_code == 405:
                resp = requests.get(
                    url,
                    timeout=timeout,
                    allow_redirects=True,
                    stream=True,
                    headers={"User-Agent": "Mozilla/5.0 ResearchKit/1.0"},
                )
            return resp.status_code < 400
        except requests.RequestException:
            return False
