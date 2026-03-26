"""处理器基础接口"""
from abc import ABC, abstractmethod
from ..core.models import Article, ResearchContext


class BaseProcessor(ABC):
    """流水线处理器基类"""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def process(self, articles: list, context: ResearchContext) -> list:
        """
        处理文章列表，返回处理后的列表（可以过滤、修改字段、增加字段）。
        :param articles: list[Article]
        :param context: 调研上下文
        :return: list[Article]
        """

    def __repr__(self):
        return f"{self.__class__.__name__}()"
