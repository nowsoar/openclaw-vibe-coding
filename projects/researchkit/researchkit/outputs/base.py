"""输出模块基础接口"""
from abc import ABC, abstractmethod
from ..core.models import Article, ResearchContext


class BaseOutput(ABC):
    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def render(
        self,
        articles: list,
        context: ResearchContext,
        template_name: str,
        output_config: dict,
    ) -> str:
        """渲染报告，返回内容字符串"""
