"""AI 相关性过滤处理器"""
import logging
from .base import BaseProcessor
from ..core.models import Article, ResearchContext
from ..core.ai_client import call_ai

logger = logging.getLogger(__name__)

DEFAULT_PROMPT = """判断以下文章是否与"{topic}"相关。
只返回0到1之间的小数，1=完全相关，0=完全不相关，不要任何解释。

标题：{title}
摘要：{summary}"""


class AIRelevanceFilter(BaseProcessor):
    """
    使用 AI 对文章打相关性分数，过滤不相关内容。
    config:
      threshold: 0.6       # 相关性阈值，低于此值过滤掉
      prompt: null          # 自定义 prompt（支持 {topic}/{title}/{summary} 变量）
      batch_size: 5         # 每批处理条数
      model: null           # 可覆盖默认模型
    """

    def process(self, articles: list, context: ResearchContext) -> list:
        # 从上层传入的 global_config（通过 metadata）
        global_config = getattr(self, "_global_config", None)
        if not global_config:
            logger.warning("未获取到 global_config，跳过 AI 相关性过滤")
            return articles

        ai_cfg = global_config.ai
        model = self.config.get("model") or ai_cfg.model_for("filter")
        threshold = float(self.config.get("threshold", 0.6))
        prompt_tpl = self.config.get("prompt") or DEFAULT_PROMPT
        batch_size = int(self.config.get("batch_size", 5))

        result = []
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i + batch_size]
            for article in batch:
                try:
                    prompt = prompt_tpl.format(
                        topic=context.topic,
                        title=article.title,
                        summary=article.summary or article.content[:300],
                    )
                    score_str = call_ai(prompt, ai_cfg, model=model, max_tokens=10)
                    score = float(score_str)
                    article.relevance_score = score
                    if score >= threshold:
                        result.append(article)
                except ValueError:
                    # AI 没有返回纯数字，保留文章
                    result.append(article)
                except Exception as e:
                    logger.warning(f"AI 相关性评分失败（{article.title[:30]}）: {e}")
                    result.append(article)  # 出错时保留

        logger.info(f"AI 相关性过滤：{len(articles)} → {len(result)} 篇（阈值={threshold}）")
        return result

