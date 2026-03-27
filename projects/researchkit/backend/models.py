"""数据库模型（SQLModel / SQLite）"""
from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel


class ResearchTaskBase(SQLModel):
    name: str
    topic: str
    query: str = ""
    keywords: str = ""          # JSON 序列化的 list[str]
    time_range_days: int = 30
    sources_config: str = "{}"  # JSON
    pipeline_config: str = "[]" # JSON
    output_config: str = "{}"   # JSON
    template: str = "competitor_analysis"
    schedule_cron: Optional[str] = None


class ResearchTask(ResearchTaskBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    status: str = "pending"     # pending | running | done | failed
    article_count: int = 0
    report_path: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ResearchTaskCreate(ResearchTaskBase):
    pass


class ResearchTaskRead(ResearchTaskBase):
    id: int
    status: str
    article_count: int
    report_path: Optional[str]
    error: Optional[str]
    created_at: datetime
    updated_at: datetime


class ResearchTaskUpdate(SQLModel):
    status: Optional[str] = None
    article_count: Optional[int] = None
    report_path: Optional[str] = None
    error: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)
