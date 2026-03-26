"""数据源基础接口"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from ..core.models import Article, ResearchContext


class BaseSource(ABC):
    """所有数据源适配器的基类"""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config

    @abstractmethod
    def fetch(
        self,
        context: ResearchContext,
        since: datetime,
        limit: int = 50,
    ) -> list:
        """
        抓取文章列表。
        :param context: 调研上下文（含主题/关键词等）
        :param since: 只抓取此时间之后的文章
        :param limit: 最多返回条数
        :return: list[Article]
        """

    def fetch_content(self, article: Article) -> str:
        """补充单篇正文。默认返回已有内容，子类可重写做二次抓取。"""
        return article.content

    def health_check(self) -> tuple:
        """检查数据源是否可用，返回 (ok: bool, message: str)"""
        return True, "OK"

    def __repr__(self):
        return f"{self.__class__.__name__}(name={self.name!r})"
