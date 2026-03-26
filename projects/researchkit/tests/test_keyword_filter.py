"""测试关键词过滤处理器"""
from researchkit.core.models import Article, ResearchContext
from researchkit.processors.keyword_filter import KeywordFilter


def _make_article(title="", summary="", content=""):
    return Article(title=title, url=f"https://example.com/{hash(title)}", summary=summary, content=content)


def _ctx():
    return ResearchContext(topic="AI工具", query="测试", keywords=["AI", "工具"])


def test_keyword_filter_any_mode_title():
    """any 模式：标题含关键词应通过"""
    f = KeywordFilter(config={"keywords": ["Cursor", "AI编程"], "mode": "any"})
    articles = [
        _make_article(title="Cursor 发布新版本"),
        _make_article(title="今天天气不错"),
    ]
    result = f.process(articles, _ctx())
    assert len(result) == 1
    assert result[0].title == "Cursor 发布新版本"


def test_keyword_filter_any_mode_content():
    """any 模式：正文含关键词也应通过"""
    f = KeywordFilter(config={"keywords": ["vibe coding"], "mode": "any"})
    articles = [
        _make_article(title="无关标题", summary="vibe coding 正在流行"),
        _make_article(title="另一篇无关文章"),
    ]
    result = f.process(articles, _ctx())
    assert len(result) == 1


def test_keyword_filter_all_mode():
    """all 模式：必须包含所有关键词"""
    f = KeywordFilter(config={"keywords": ["AI", "编程"], "mode": "all"})
    articles = [
        _make_article(title="AI 编程工具"),
        _make_article(title="AI 产品"),
        _make_article(title="编程教程"),
    ]
    result = f.process(articles, _ctx())
    assert len(result) == 1
    assert result[0].title == "AI 编程工具"


def test_keyword_filter_empty_keywords_pass_all():
    """没有关键词时应返回所有文章"""
    f = KeywordFilter(config={"keywords": []})
    articles = [_make_article(title=f"文章{i}") for i in range(5)]
    result = f.process(articles, ResearchContext(topic="测试", query="测试"))
    assert len(result) == 5


def test_keyword_filter_case_insensitive():
    """关键词匹配应不区分大小写"""
    f = KeywordFilter(config={"keywords": ["cursor"], "mode": "any"})
    articles = [_make_article(title="CURSOR 发布新功能")]
    result = f.process(articles, _ctx())
    assert len(result) == 1
