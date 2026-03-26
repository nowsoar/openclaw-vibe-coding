"""核心数据模型"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import hashlib


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Article:
    """抓取到的单篇文章"""
    title: str
    url: str
    source_type: str = ""        # wechat / xiaohongshu / web / rss
    source_name: str = ""        # 来源名称，如"36氪"
    content: str = ""            # 正文
    summary: str = ""            # 摘要（来源自带或 AI 生成）
    author: str = ""
    published_at: Optional[datetime] = None
    fetched_at: Optional[datetime] = None
    tags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    relevance_score: float = 0.0
    is_included: bool = False

    @property
    def id(self) -> str:
        """基于 URL 生成唯一 ID"""
        return hashlib.md5(self.url.encode()).hexdigest()

    def __repr__(self):
        return f"Article(title={self.title[:30]!r}, source={self.source_name!r})"


@dataclass
class ResearchContext:
    """调研任务的研究意图"""
    topic: str                          # 调研主题
    query: str                          # 详细研究目的（自然语言）
    keywords: list = field(default_factory=list)  # 核心关键词
    time_range_days: int = 30           # 抓取时间范围
    language: str = "zh"                # 输出语言


@dataclass
class ResearchTask:
    """完整的调研任务"""
    name: str
    context: ResearchContext
    sources_config: dict = field(default_factory=dict)
    pipeline_config: list = field(default_factory=list)
    output_config: dict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    articles: list = field(default_factory=list)
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
