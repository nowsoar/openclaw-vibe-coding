"""统一 AI 调用封装，支持 OpenAI 和 Anthropic SDK"""
from __future__ import annotations


def call_ai(prompt: str, ai_cfg, model: str = None, max_tokens: int = 500) -> str:
    """
    统一调用 AI 接口，根据 ai_cfg.api_type 选择对应 SDK。

    :param prompt:     用户 prompt
    :param ai_cfg:     AIConfig 实例
    :param model:      覆盖默认模型（可选）
    :param max_tokens: 最大输出 token 数
    :return:           模型返回的文本字符串
    """
    model = model or ai_cfg.default_model

    if ai_cfg.api_type == "anthropic":
        from anthropic import Anthropic
        client = Anthropic(api_key=ai_cfg.api_key, base_url=ai_cfg.base_url)
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    else:
        from openai import OpenAI
        client = OpenAI(api_key=ai_cfg.api_key, base_url=ai_cfg.base_url)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()
