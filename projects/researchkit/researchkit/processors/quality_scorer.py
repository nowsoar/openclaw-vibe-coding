"""内容质量评分处理器 — 自动判断文章信息密度（规则 + 可选 AI 评分）"""
import logging
import re

from .base import BaseProcessor
from ..core.models import Article, ResearchContext

logger = logging.getLogger(__name__)


class QualityScorer(BaseProcessor):
    """
    对文章进行信息密度评分（0.0 ~ 1.0）。

    评分模式（``mode`` 配置项）：
      - ``heuristic``（默认）：纯规则评分，无 API 消耗
      - ``ai``：调用 OpenAI API 对文章进行评分
      - ``hybrid``：AI 评分 + 规则评分取平均值

    其他配置：
      - ``threshold``：过滤阈值（0.0 = 不过滤）
      - ``filter``：True 则过滤低于阈值的文章
      - ``sort``：True 则按分数降序排列（默认 True）
      - ``ai_sample_chars``：送给 AI 的文章文本截断长度（默认 800）
    """

    def process(self, articles: list, context: ResearchContext) -> list:
        threshold = float(self.config.get("threshold", 0.0))
        mode = self.config.get("mode", "heuristic")
        do_filter = self.config.get("filter", False)

        for article in articles:
            if mode == "ai":
                score = self._ai_score(article, context)
            elif mode == "hybrid":
                h = self._heuristic_score(article)
                a = self._ai_score(article, context)
                score = round((h + a) / 2, 3)
            else:
                score = self._heuristic_score(article)
            article.quality_score = score  # 动态附加属性

        if do_filter and threshold > 0:
            before = len(articles)
            articles = [a for a in articles if getattr(a, "quality_score", 0) >= threshold]
            logger.info(f"质量过滤：{before - len(articles)} 篇低质量文章已移除（阈值 {threshold}）")

        if self.config.get("sort", True):
            articles.sort(key=lambda a: getattr(a, "quality_score", 0), reverse=True)

        return articles

    def _heuristic_score(self, article: Article) -> float:
        scores = []
        text = article.content or article.summary or ""

        # 1. 内容长度（500字 → 0.5，2000字 → 1.0）
        scores.append(min(1.0, len(text) / 2000) * 0.4)

        # 2. 数字 / 数据密度
        data_matches = len(re.findall(r'\d[\d,.%亿万千百]+|\d{4}年|\d+\.\d+', text))
        scores.append(min(1.0, data_matches / 10) * 0.25)

        # 3. 段落结构
        paragraphs = [p for p in re.split(r'\n{2,}', text) if p.strip()]
        scores.append(min(1.0, len(paragraphs) / 5) * 0.15)

        # 4. 标题信息量
        title = article.title or ""
        title_score = min(1.0, len(title) / 30)
        if re.search(r'\d', title):
            title_score = min(1.0, title_score + 0.2)
        scores.append(title_score * 0.1)

        # 5. 含摘要加分
        scores.append((1.0 if article.summary and len(article.summary) > 20 else 0.0) * 0.1)

        return round(sum(scores), 3)

    def _ai_score(self, article: Article, context: ResearchContext) -> float:
        global_cfg = getattr(self, "_global_config", None)
        if global_cfg is None:
            logger.debug("QualityScorer: 未注入 _global_config，降级为规则评分")
            return self._heuristic_score(article)

        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=global_cfg.ai.api_key,
                base_url=global_cfg.ai.base_url or None,
            )
            sample_chars = self.config.get("ai_sample_chars", 800)
            text_sample = (article.content or article.summary or "")[:sample_chars]
            prompt = (
                f"请对以下文章的信息密度打分（0.0 ~ 1.0），"
                f"仅输出一个两位小数的数字，不要任何额外文字。\n\n"
                f"主题背景：{context.topic}\n"
                f"标题：{article.title}\n"
                f"正文节选：{text_sample}"
            )
            model = global_cfg.ai.model_for("quality_scorer")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
                temperature=0,
            )
            raw = resp.choices[0].message.content.strip()
            match = re.search(r'[\d.]+', raw)
            score = float(match.group()) if match else 0.5
            return round(max(0.0, min(1.0, score)), 3)
        except Exception as exc:
            logger.warning(f"AI 质量评分失败，降级为规则评分：{exc}")
            return self._heuristic_score(article)
