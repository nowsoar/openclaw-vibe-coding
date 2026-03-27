"""ResearchKit 插件机制

插件分为三类：
- source   数据源插件（BaseSource 子类）
- processor 处理器插件（BaseProcessor 子类）
- output   输出格式插件（BaseOutput 子类）

注册方式::

    from researchkit.plugins import register_plugin, PluginType

    @register_plugin(PluginType.SOURCE, "my_source")
    class MySource(BaseSource):
        ...

或在 pyproject.toml 中声明入口点::

    [project.entry-points."researchkit.sources"]
    my_source = "my_package.sources:MySource"
"""
from __future__ import annotations

import importlib
import importlib.metadata
import logging
from enum import Enum
from typing import Any, Type

logger = logging.getLogger(__name__)


class PluginType(str, Enum):
    SOURCE = "source"
    PROCESSOR = "processor"
    OUTPUT = "output"


# 内部注册表：{PluginType: {name: cls}}
_REGISTRY: dict[PluginType, dict[str, type]] = {
    PluginType.SOURCE: {},
    PluginType.PROCESSOR: {},
    PluginType.OUTPUT: {},
}

# 入口点分组名称映射
_ENTRY_POINT_GROUPS = {
    PluginType.SOURCE: "researchkit.sources",
    PluginType.PROCESSOR: "researchkit.processors",
    PluginType.OUTPUT: "researchkit.outputs",
}


def register_plugin(plugin_type: PluginType, name: str):
    """装饰器：将类注册为 ResearchKit 插件。"""
    def decorator(cls: type) -> type:
        _REGISTRY[plugin_type][name] = cls
        logger.debug(f"已注册插件 [{plugin_type.value}] {name} = {cls.__qualname__}")
        return cls
    return decorator


def get_plugin(plugin_type: PluginType, name: str) -> type | None:
    """按类型和名称查找插件类（先查内置注册表，再尝试入口点）。"""
    cls = _REGISTRY[plugin_type].get(name)
    if cls:
        return cls
    # 尝试从已安装包的入口点加载
    return _load_from_entry_point(plugin_type, name)


def list_plugins(plugin_type: PluginType) -> dict[str, type]:
    """列出某类型的所有已注册插件（含入口点）。"""
    all_plugins: dict[str, type] = {}
    # 入口点优先被内置覆盖
    all_plugins.update(_load_all_entry_points(plugin_type))
    all_plugins.update(_REGISTRY[plugin_type])
    return all_plugins


def _load_from_entry_point(plugin_type: PluginType, name: str) -> type | None:
    group = _ENTRY_POINT_GROUPS[plugin_type]
    try:
        eps = importlib.metadata.entry_points(group=group)
        for ep in eps:
            if ep.name == name:
                return ep.load()
    except Exception as e:
        logger.debug(f"入口点加载失败 [{group}:{name}]: {e}")
    return None


def _load_all_entry_points(plugin_type: PluginType) -> dict[str, type]:
    group = _ENTRY_POINT_GROUPS[plugin_type]
    result: dict[str, type] = {}
    try:
        for ep in importlib.metadata.entry_points(group=group):
            try:
                result[ep.name] = ep.load()
            except Exception as e:
                logger.debug(f"入口点加载失败 [{group}:{ep.name}]: {e}")
    except Exception as e:
        logger.debug(f"入口点枚举失败 [{group}]: {e}")
    return result


# ─── 内置插件自动注册 ────────────────────────────────────────────────────────

def _register_builtins():
    """将 researchkit 内置的 source/processor/output 注册到插件系统。"""
    _safe_register_source("wechat", "researchkit.sources.wechat", "WeChatSource")
    _safe_register_source("rss", "researchkit.sources.rss", "RSSSource")
    _safe_register_source("web", "researchkit.sources.web", "WebSource")
    _safe_register_source("xiaohongshu", "researchkit.sources.xiaohongshu", "XiaohongshuSource")

    _safe_register_processor("keyword_filter", "researchkit.processors.keyword_filter", "KeywordFilter")
    _safe_register_processor("deduplicator", "researchkit.processors.deduplicator", "Deduplicator")
    _safe_register_processor("ai_relevance", "researchkit.processors.ai_relevance", "AIRelevanceFilter")
    _safe_register_processor("ai_summarize", "researchkit.processors.ai_summarize", "AISummarizer")
    _safe_register_processor("content_fetcher", "researchkit.processors.content_fetcher", "ContentFetcher")
    _safe_register_processor("reference_validator", "researchkit.processors.reference_validator", "ReferenceValidator")
    _safe_register_processor("quality_scorer", "researchkit.processors.quality_scorer", "QualityScorer")

    _safe_register_output("markdown", "researchkit.outputs.markdown", "MarkdownOutput")
    _safe_register_output("feishu", "researchkit.outputs.feishu", "FeishuOutput")
    _safe_register_output("pdf", "researchkit.outputs.pdf", "PDFOutput")


def _safe_register_source(name: str, module: str, cls_name: str):
    _safe_register(PluginType.SOURCE, name, module, cls_name)


def _safe_register_processor(name: str, module: str, cls_name: str):
    _safe_register(PluginType.PROCESSOR, name, module, cls_name)


def _safe_register_output(name: str, module: str, cls_name: str):
    _safe_register(PluginType.OUTPUT, name, module, cls_name)


def _safe_register(plugin_type: PluginType, name: str, module: str, cls_name: str):
    try:
        mod = importlib.import_module(module)
        cls = getattr(mod, cls_name)
        _REGISTRY[plugin_type][name] = cls
    except Exception as e:
        logger.debug(f"内置插件注册跳过 [{name}]: {e}")


_register_builtins()
