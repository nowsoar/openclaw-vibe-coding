"""流水线调度引擎"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional
from .models import ResearchTask, ResearchContext, TaskStatus
from .config import GlobalConfig

logger = logging.getLogger(__name__)


def _build_source(source_type: str, name: str, config: dict):
    """根据类型实例化数据源"""
    from ..sources.wechat import WeChatSource
    from ..sources.rss import RSSSource
    from ..sources.web import WebSource
    from ..sources.xiaohongshu import XiaohongshuSource

    mapping = {
        "wechat": WeChatSource,
        "rss": RSSSource,
        "web": WebSource,
        "xiaohongshu": XiaohongshuSource,
        "xhs": XiaohongshuSource,
    }
    cls = mapping.get(source_type)
    if not cls:
        raise ValueError(f"未知数据源类型：{source_type}")
    return cls(name=name, config=config)


def _build_processor(step: dict, global_config: GlobalConfig):
    """根据步骤配置实例化处理器"""
    from ..processors.keyword_filter import KeywordFilter
    from ..processors.deduplicator import Deduplicator
    from ..processors.ai_relevance import AIRelevanceFilter
    from ..processors.ai_summarize import AISummarizer
    from ..processors.content_fetcher import ContentFetcherProcessor
    from ..processors.reference_validator import ReferenceValidator
    from ..processors.citation_validator import CitationValidator
    from ..processors.quality_scorer import QualityScorer

    step_type = step.get("step", "")
    cfg = {k: v for k, v in step.items() if k != "step"}

    mapping = {
        "keyword_filter": KeywordFilter,
        "dedup": Deduplicator,
        "ai_relevance": AIRelevanceFilter,
        "ai_summarize": AISummarizer,
        "content_fetcher": ContentFetcherProcessor,
        "content_fetch": ContentFetcherProcessor,
        "citation_validator": CitationValidator,
        "reference_validator": ReferenceValidator,
        "reference_validate": ReferenceValidator,
        "quality_scorer": QualityScorer,
        "quality_score": QualityScorer,
    }
    cls = mapping.get(step_type)
    if not cls:
        raise ValueError(f"未知处理器类型：{step_type}")

    processor = cls(config=cfg)
    processor._global_config = global_config  # 传递全局配置（供 AI 处理器使用）
    return processor


class Pipeline:
    """调研流水线：抓取 → 处理 → 输出"""

    def __init__(self, task: ResearchTask, global_config: GlobalConfig):
        self.task = task
        self.global_config = global_config

    def run(self, progress_callback: Optional[Callable] = None) -> str:
        """
        执行完整流水线，返回报告 Markdown 文本。
        :param progress_callback: 进度回调 fn(stage, current, total, message)
        """
        def notify(stage, current, total, msg=""):
            if progress_callback:
                progress_callback(stage, current, total, msg)
            else:
                logger.info(f"[{stage}] {current}/{total} {msg}")

        context = self.task.context
        since = datetime.now(timezone.utc) - timedelta(days=context.time_range_days)

        # ── 阶段一：并行抓取各数据源 ──
        notify("fetch", 0, 1, "开始抓取数据源...")
        all_articles = self._fetch_all(context, since, notify)
        notify("fetch", 1, 1, f"抓取完成，共 {len(all_articles)} 篇")

        # ── 阶段二：顺序执行处理器 ──
        articles = all_articles
        pipeline_steps = self.task.pipeline_config
        for i, step_cfg in enumerate(pipeline_steps):
            step_name = step_cfg.get("step", "")
            notify("process", i, len(pipeline_steps), f"执行 {step_name}...")
            try:
                processor = _build_processor(step_cfg, self.global_config)
                articles = processor.process(articles, context)
            except Exception as e:
                logger.warning(f"处理器 {step_name} 失败，跳过: {e}")

        notify("process", len(pipeline_steps), len(pipeline_steps),
               f"处理完成，剩余 {len(articles)} 篇")
        self.task.articles = articles

        # ── 阶段三：生成报告 ──
        notify("output", 0, 1, "生成报告...")
        output_format = self.task.output_config.get("format", "markdown")
        output = self._build_output(output_format)
        output._global_config = self.global_config

        template_name = self.task.output_config.get("template", "competitor_analysis")
        report_md = output.render(articles, context, template_name, self.task.output_config)
        notify("output", 1, 1, "报告生成完成")

        return report_md

    def _build_output(self, output_format: str):
        """根据输出格式实例化 Output 对象"""
        from ..outputs.markdown import MarkdownOutput
        from ..outputs.feishu import FeishuOutput
        from ..outputs.pdf import PDFOutput

        mapping = {
            "markdown": MarkdownOutput,
            "md": MarkdownOutput,
            "feishu": FeishuOutput,
            "pdf": PDFOutput,
        }
        cls = mapping.get(output_format, MarkdownOutput)
        return cls(config=self.task.output_config)

    def _fetch_all(self, context: ResearchContext, since: datetime, notify) -> list:
        """并行抓取所有已启用的数据源"""
        sources_cfg = self.task.sources_config
        tasks = []

        for source_type, source_cfg in sources_cfg.items():
            if not source_cfg.get("enabled", False):
                continue
            try:
                source = _build_source(source_type, source_type, source_cfg)
                tasks.append((source_type, source))
            except ValueError as e:
                logger.warning(str(e))

        if not tasks:
            logger.warning("没有启用任何数据源")
            return []

        all_articles = []
        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            future_map = {
                executor.submit(src.fetch, context, since, 50): name
                for name, src in tasks
            }
            for future in as_completed(future_map):
                source_name = future_map[future]
                try:
                    articles = future.result()
                    all_articles.extend(articles)
                    notify("fetch", 1, len(tasks), f"{source_name} 抓取 {len(articles)} 篇")
                except Exception as e:
                    logger.warning(f"{source_name} 抓取失败: {e}")

        return all_articles
