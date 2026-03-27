"""Phase 2 新增功能单元测试"""
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from researchkit.core.models import Article, ResearchContext


# ──────────────────────────────────────────────────────────────────────────────
# 辅助工厂
# ──────────────────────────────────────────────────────────────────────────────

def make_article(**kwargs) -> Article:
    defaults = dict(
        title="测试文章",
        url="https://example.com/article",
        source_type="web",
        source_name="test",
        content="",
        summary="",
    )
    defaults.update(kwargs)
    return Article(**defaults)


def make_context(**kwargs) -> ResearchContext:
    defaults = dict(topic="人工智能", query="AI 趋势", keywords=["AI", "大模型"])
    defaults.update(kwargs)
    return ResearchContext(**defaults)


# ──────────────────────────────────────────────────────────────────────────────
# ContentFetcherProcessor
# ──────────────────────────────────────────────────────────────────────────────

class TestContentFetcher:
    def test_skip_articles_with_content(self):
        """已有正文的文章不应再发起请求"""
        from researchkit.processors.content_fetcher import ContentFetcherProcessor
        proc = ContentFetcherProcessor(config={})
        articles = [make_article(content="已有正文内容")]
        with patch("researchkit.processors.content_fetcher.requests.get") as mock_get:
            result = proc.process(articles, make_context())
        mock_get.assert_not_called()
        assert result[0].content == "已有正文内容"

    def test_fetch_fills_content(self):
        """内容为空时应抓取正文"""
        from researchkit.processors.content_fetcher import ContentFetcherProcessor
        proc = ContentFetcherProcessor(config={"retries": 1})
        articles = [make_article(content="")]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body><article>文章正文内容在这里</article></body></html>"
        mock_resp.raise_for_status = MagicMock()
        with patch("researchkit.processors.content_fetcher.requests.get", return_value=mock_resp):
            result = proc.process(articles, make_context())
        assert "文章正文内容在这里" in result[0].content

    def test_retry_on_server_error(self):
        """服务器 5xx 应触发重试"""
        from researchkit.processors.content_fetcher import _fetch_with_retry
        import requests as req_lib
        err_resp = MagicMock()
        err_resp.status_code = 500
        exc = req_lib.exceptions.HTTPError(response=err_resp)
        with patch("researchkit.processors.content_fetcher.requests.get", side_effect=exc):
            with patch("researchkit.processors.content_fetcher.time.sleep"):
                result = _fetch_with_retry("https://example.com", 5, 2, 1000)
        assert result == ""

    def test_no_retry_on_client_error(self):
        """4xx 错误不应重试"""
        from researchkit.processors.content_fetcher import _fetch_with_retry
        import requests as req_lib
        err_resp = MagicMock()
        err_resp.status_code = 404
        exc = req_lib.exceptions.HTTPError(response=err_resp)
        call_count = 0

        def side_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            raise exc

        with patch("researchkit.processors.content_fetcher.requests.get", side_effect=side_effect):
            result = _fetch_with_retry("https://example.com", 5, 3, 1000)
        assert call_count == 1  # 只调用一次，不重试
        assert result == ""

    def test_site_specific_selector(self):
        """使用站点特定选择器提取正文"""
        from researchkit.processors.content_fetcher import _extract_content
        html = '<html><body><div class="Post-RichTextContainer">知乎文章正文</div></body></html>'
        result = _extract_content(html, "https://zhihu.com/p/123", 5000)
        assert "知乎文章正文" in result


# ──────────────────────────────────────────────────────────────────────────────
# CitationValidator
# ──────────────────────────────────────────────────────────────────────────────

class TestCitationValidator:
    def test_valid_links_kept(self):
        from researchkit.processors.citation_validator import CitationValidator
        proc = CitationValidator(config={"remove_invalid": True, "max_workers": 2})
        articles = [
            make_article(url="https://example.com/ok"),
            make_article(url="https://example.com/good", title="好文章"),
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("researchkit.processors.reference_validator.requests.head", return_value=mock_resp):
            result = proc.process(articles, make_context())
        assert len(result) == 2

    def test_invalid_links_filtered(self):
        from researchkit.processors.citation_validator import CitationValidator
        proc = CitationValidator(config={"remove_invalid": True, "max_workers": 2})
        articles = [make_article(url="https://dead.example.com/404")]
        import requests as req_lib
        with patch(
            "researchkit.processors.reference_validator.requests.head",
            side_effect=req_lib.RequestException("connection refused"),
        ):
            result = proc.process(articles, make_context())
        assert len(result) == 0

    def test_keep_invalid_by_default(self):
        from researchkit.processors.citation_validator import CitationValidator
        proc = CitationValidator(config={"remove_invalid": False, "max_workers": 2})
        articles = [make_article(url="https://dead.example.com")]
        import requests as req_lib
        with patch(
            "researchkit.processors.reference_validator.requests.head",
            side_effect=req_lib.RequestException("timeout"),
        ):
            result = proc.process(articles, make_context())
        assert len(result) == 1  # 不过滤，只记录


# ──────────────────────────────────────────────────────────────────────────────
# QualityScorer
# ──────────────────────────────────────────────────────────────────────────────

class TestQualityScorer:
    def test_heuristic_score_range(self):
        from researchkit.processors.quality_scorer import QualityScorer
        proc = QualityScorer(config={"mode": "heuristic", "sort": False})
        articles = [
            make_article(content="短内容"),
            make_article(
                content="这是一篇详细的分析文章，\n\n包含多个段落。\n\n2024年市场数据显示：AI市场规模达1000亿，增速达30%。\n\n深度分析如下：...",
                summary="详细摘要内容超过20个字符以上",
            ),
        ]
        result = proc.process(articles, make_context())
        for a in result:
            assert 0.0 <= a.quality_score <= 1.0
        # 长文章得分应高于短文章
        scores = {a.content[:3]: a.quality_score for a in result}
        assert scores["这是一"] > scores["短内容"]

    def test_filter_mode(self):
        from researchkit.processors.quality_scorer import QualityScorer
        proc = QualityScorer(config={"mode": "heuristic", "filter": True, "threshold": 0.5, "sort": False})
        articles = [
            make_article(content="短"),
            make_article(
                content="x" * 2000 + "2024年 数据：1000亿\n\n段落2\n\n段落3\n\n段落4\n\n段落5",
                summary="这是一个很长的摘要超过二十个字符",
                title="2024年AI市场深度分析",
            ),
        ]
        result = proc.process(articles, make_context())
        assert len(result) < 2  # 至少过滤掉了短文章

    def test_ai_score_fallback_without_config(self):
        from researchkit.processors.quality_scorer import QualityScorer
        proc = QualityScorer(config={"mode": "ai", "sort": False})
        # 没有注入 _global_config，应降级为规则评分
        articles = [make_article(content="测试内容")]
        result = proc.process(articles, make_context())
        assert hasattr(result[0], "quality_score")
        assert 0.0 <= result[0].quality_score <= 1.0

    def test_sort_descending(self):
        from researchkit.processors.quality_scorer import QualityScorer
        proc = QualityScorer(config={"mode": "heuristic", "sort": True})
        articles = [
            make_article(content="短"),
            make_article(content="中等长度内容" * 10),
            make_article(content="很长很长的内容" * 100),
        ]
        result = proc.process(articles, make_context())
        scores = [a.quality_score for a in result]
        assert scores == sorted(scores, reverse=True)


# ──────────────────────────────────────────────────────────────────────────────
# XiaohongshuSource
# ──────────────────────────────────────────────────────────────────────────────

class TestXiaohongshuSource:
    def test_health_check_no_cookie(self):
        from researchkit.sources.xiaohongshu import XiaohongshuSource
        src = XiaohongshuSource(name="xhs", config={})
        result = src.health_check()
        # 没有配置 cookie/auth，应返回失败状态
        assert result[0] is False or result.get("status") in ("error", "warn", False)

    def test_fetch_returns_empty_without_auth(self):
        """未配置 cookie 时应优雅地返回空列表"""
        from researchkit.sources.xiaohongshu import XiaohongshuSource
        src = XiaohongshuSource(name="xhs", config={})
        ctx = make_context()
        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        # 不应抛出异常
        articles = src.fetch(ctx, since, limit=5)
        assert isinstance(articles, list)


# ──────────────────────────────────────────────────────────────────────────────
# FeishuOutput
# ──────────────────────────────────────────────────────────────────────────────

class TestFeishuOutput:
    def test_skip_without_credentials(self):
        """未配置飞书凭据时，应静默跳过，返回 Markdown"""
        from researchkit.outputs.feishu import FeishuOutput
        output = FeishuOutput(config={})
        output._global_config = None

        articles = [make_article(title="飞书测试文章", content="内容")]
        ctx = make_context()

        with patch("researchkit.outputs.markdown.MarkdownOutput._ai_synthesize", return_value="# 测试报告\n内容"):
            result = output.render(articles, ctx, "trend_report", {})
        assert isinstance(result, str)

    def test_md_to_feishu_blocks(self):
        from researchkit.outputs.feishu import FeishuOutput
        output = FeishuOutput(config={})
        blocks = output._md_to_feishu_blocks("# 标题\n## 二级\n普通文本")
        assert any(b.get("block_type") == "heading1" for b in blocks)
        assert any(b.get("block_type") == "heading2" for b in blocks)
        assert any(b.get("block_type") == "paragraph" for b in blocks)


# ──────────────────────────────────────────────────────────────────────────────
# Pipeline 处理器注册
# ──────────────────────────────────────────────────────────────────────────────

class TestPipelineRegistration:
    def _make_global_config(self):
        from researchkit.core.config import GlobalConfig, AIConfig
        cfg = GlobalConfig(ai=AIConfig(api_key="test"))
        return cfg

    def test_content_fetcher_registered(self):
        from researchkit.core.pipeline import _build_processor
        proc = _build_processor({"step": "content_fetcher"}, self._make_global_config())
        from researchkit.processors.content_fetcher import ContentFetcherProcessor
        assert isinstance(proc, ContentFetcherProcessor)

    def test_citation_validator_registered(self):
        from researchkit.core.pipeline import _build_processor
        proc = _build_processor({"step": "citation_validator"}, self._make_global_config())
        from researchkit.processors.citation_validator import CitationValidator
        assert isinstance(proc, CitationValidator)

    def test_quality_scorer_registered(self):
        from researchkit.core.pipeline import _build_processor
        proc = _build_processor({"step": "quality_scorer"}, self._make_global_config())
        from researchkit.processors.quality_scorer import QualityScorer
        assert isinstance(proc, QualityScorer)

    def test_xiaohongshu_source_registered(self):
        from researchkit.core.pipeline import _build_source
        src = _build_source("xiaohongshu", "xhs", {})
        from researchkit.sources.xiaohongshu import XiaohongshuSource
        assert isinstance(src, XiaohongshuSource)
