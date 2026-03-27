"""Pydantic schemas for the ResearchKit API"""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class TaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    topic: str = Field(..., min_length=1)
    query: str = ""
    keywords: list[str] = []
    time_range_days: int = Field(default=30, ge=1, le=365)
    sources_config: dict[str, Any] = {}
    pipeline_config: list[dict[str, Any]] = []
    output_config: dict[str, Any] = {}


class TaskResponse(BaseModel):
    id: str
    name: str
    topic: str
    query: str = ""
    keywords: list[str] = []
    time_range_days: int = 30
    sources_config: dict[str, Any] = {}
    pipeline_config: list[dict[str, Any]] = []
    output_config: dict[str, Any] = {}
    status: TaskStatus = TaskStatus.PENDING
    article_count: int = 0
    report_path: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class SourceStatusResponse(BaseModel):
    name: str
    status: str  # "ok" | "error" | "warn"
    message: str


class ProgressEvent(BaseModel):
    type: str  # "progress" | "done" | "error" | "ping"
    stage: Optional[str] = None
    current: int = 0
    total: int = 1
    message: str = ""
    report_path: Optional[str] = None
    article_count: Optional[int] = None
