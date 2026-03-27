"""引用验证处理器 — 验证来源链接可访问性（ROADMAP Phase 2）"""
# 复用 ReferenceValidator 的完整实现，并以 CitationValidator 作为规范名称对外暴露
from .reference_validator import ReferenceValidator as CitationValidator

__all__ = ["CitationValidator"]
