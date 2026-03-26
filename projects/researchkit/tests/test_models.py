"""测试核心数据模型"""
from datetime import datetime
from researchkit.core.models import Article, ResearchContext, ResearchTask, TaskStatus


def test_article_id_deterministic():
    """相同 URL 的文章应该生成相同 ID"""
    a1 = Article(title="测试", url="https://example.com/article/1")
    a2 = Article(title="测试2", url="https://example.com/article/1")
    assert a1.id == a2.id


def test_article_id_different():
    """不同 URL 的文章应该生成不同 ID"""
    a1 = Article(title="测试", url="https://example.com/1")
    a2 = Article(title="测试", url="https://example.com/2")
    assert a1.id != a2.id


def test_article_defaults():
    """Article 默认值应该合理"""
    a = Article(title="标题", url="https://example.com")
    assert a.content == ""
    assert a.summary == ""
    assert a.relevance_score == 0.0
    assert a.is_included is False
    assert a.tags == []
    assert a.metadata == {}


def test_research_context_defaults():
    """ResearchContext 默认值"""
    ctx = ResearchContext(topic="AI调研", query="研究AI工具")
    assert ctx.time_range_days == 30
    assert ctx.language == "zh"
    assert ctx.keywords == []


def test_research_task_created_at():
    """ResearchTask 应该自动设置创建时间"""
    ctx = ResearchContext(topic="测试", query="测试调研")
    task = ResearchTask(name="测试任务", context=ctx)
    assert task.created_at is not None
    assert isinstance(task.created_at, datetime)


def test_task_status_enum():
    ctx = ResearchContext(topic="测试", query="测试")
    task = ResearchTask(name="任务", context=ctx)
    assert task.status == TaskStatus.PENDING
    task.status = TaskStatus.RUNNING
    assert task.status == TaskStatus.RUNNING
