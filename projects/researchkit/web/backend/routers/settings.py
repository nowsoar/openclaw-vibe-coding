"""Settings 路由 — 用户自行配置 AI Key 和微信凭证"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/settings", tags=["settings"])

_CONFIG_DIR = Path.home() / ".researchkit"
_CONFIG_FILE = _CONFIG_DIR / "config.yaml"
_WECHAT_AUTH_FILE = _CONFIG_DIR / "wechat-auth.json"

# ─── 辅助函数 ─────────────────────────────────────────────────────────────────


def _load_config() -> dict:
    """加载 ~/.researchkit/config.yaml，不存在返回空字典"""
    if not _CONFIG_FILE.exists():
        return {}
    with open(_CONFIG_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_config(data: dict) -> None:
    """保存配置到 ~/.researchkit/config.yaml"""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


def _load_wechat_auth() -> dict:
    """加载 ~/.researchkit/wechat-auth.json，不存在返回空字典"""
    if not _WECHAT_AUTH_FILE.exists():
        return {}
    with open(_WECHAT_AUTH_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_wechat_auth(data: dict) -> None:
    """保存微信凭证到 ~/.researchkit/wechat-auth.json"""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_WECHAT_AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _mask_api_key(key: str) -> str:
    """脱敏：只显示前6后4位"""
    if not key:
        return ""
    if len(key) <= 10:
        return "*" * len(key)
    return key[:6] + "****" + key[-4:]


def _parse_curl(curl_str: str) -> dict:
    """从 curl 命令中提取 cookie 和 token"""
    cookie_match = re.search(r"-b '([^']+)'", curl_str)
    # 也支持双引号
    if not cookie_match:
        cookie_match = re.search(r'-b "([^"]+)"', curl_str)
    token_match = re.search(r'token=(\d+)', curl_str)
    return {
        "cookie": cookie_match.group(1) if cookie_match else "",
        "token": token_match.group(1) if token_match else "",
    }


# ─── Pydantic 模型 ────────────────────────────────────────────────────────────

class SettingsUpdate(BaseModel):
    ai_api_key: Optional[str] = None
    ai_base_url: Optional[str] = None
    ai_model: Optional[str] = None
    ai_api_type: Optional[str] = None
    ai_cost_limit: Optional[float] = None
    wechat_cookie: Optional[str] = None
    wechat_token: Optional[str] = None
    curl_command: Optional[str] = None
    output_dir: Optional[str] = None


# ─── GET /api/settings ────────────────────────────────────────────────────────

@router.get("")
async def get_settings():
    """返回当前配置（api_key 脱敏）"""
    cfg = _load_config()
    ai_cfg = cfg.get("ai", {})
    raw_key = ai_cfg.get("api_key", "")
    # 处理 ${ENV_VAR} 形式
    if raw_key.startswith("${") and raw_key.endswith("}"):
        import os
        raw_key = os.environ.get(raw_key[2:-1], "")

    wechat = _load_wechat_auth()
    wechat_configured = bool(wechat.get("cookie") or wechat.get("token"))

    return {
        "ai": {
            "api_key_set": bool(raw_key),
            "api_key_preview": _mask_api_key(raw_key),
            "base_url": ai_cfg.get("base_url", "https://api.openai.com/v1"),
            "default_model": ai_cfg.get("default_model", "gpt-4o-mini"),
            "api_type": ai_cfg.get("api_type", "openai"),
            "cost_limit_usd": float(ai_cfg.get("cost_limit_usd", 5.0)),
        },
        "wechat": {
            "configured": wechat_configured,
            "token": wechat.get("token", ""),
            "updated_at": wechat.get("updated_at", ""),
        },
        "output_dir": cfg.get("output", {}).get("dir", "~/Documents/research/"),
    }


# ─── POST /api/settings ──────────────────────────────────────────────────────

@router.post("")
async def update_settings(body: SettingsUpdate):
    """更新配置并保存到文件"""
    cfg = _load_config()

    # ── AI 配置 ──
    ai_cfg = cfg.setdefault("ai", {})
    if body.ai_api_key is not None:
        ai_cfg["api_key"] = body.ai_api_key
    if body.ai_base_url is not None:
        ai_cfg["base_url"] = body.ai_base_url
    if body.ai_model is not None:
        ai_cfg["default_model"] = body.ai_model
    if body.ai_api_type is not None:
        if body.ai_api_type not in ("openai", "anthropic"):
            raise HTTPException(status_code=400, detail="api_type 只支持 openai 或 anthropic")
        ai_cfg["api_type"] = body.ai_api_type
    if body.ai_cost_limit is not None:
        ai_cfg["cost_limit_usd"] = body.ai_cost_limit

    # ── 输出目录 ──
    if body.output_dir is not None:
        cfg.setdefault("output", {})["dir"] = body.output_dir

    _save_config(cfg)

    # ── 微信凭证 ──
    wechat_auth = _load_wechat_auth()

    # 优先从 curl 命令解析
    if body.curl_command:
        parsed = _parse_curl(body.curl_command)
        if parsed["cookie"]:
            wechat_auth["cookie"] = parsed["cookie"]
        if parsed["token"]:
            wechat_auth["token"] = parsed["token"]
        wechat_auth["updated_at"] = datetime.now().isoformat()
        _save_wechat_auth(wechat_auth)
    elif body.wechat_cookie or body.wechat_token:
        if body.wechat_cookie:
            wechat_auth["cookie"] = body.wechat_cookie
        if body.wechat_token:
            wechat_auth["token"] = body.wechat_token
        wechat_auth["updated_at"] = datetime.now().isoformat()
        _save_wechat_auth(wechat_auth)

    return {"ok": True, "message": "配置已保存"}


# ─── POST /api/settings/test-ai ──────────────────────────────────────────────

@router.post("/test-ai")
async def test_ai_connection():
    """用当前配置发一条简单 prompt 测试 AI 连接"""
    cfg = _load_config()
    ai_cfg = cfg.get("ai", {})
    api_key = ai_cfg.get("api_key", "")
    if api_key.startswith("${") and api_key.endswith("}"):
        import os
        api_key = os.environ.get(api_key[2:-1], "")

    if not api_key:
        return {"ok": False, "message": "API Key 未配置，请先在设置页面填写"}

    base_url = ai_cfg.get("base_url", "https://api.openai.com/v1")
    model = ai_cfg.get("default_model", "gpt-4o-mini")
    api_type = ai_cfg.get("api_type", "openai")

    try:
        if api_type == "anthropic":
            import anthropic  # type: ignore
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model=model,
                max_tokens=16,
                messages=[{"role": "user", "content": "hi"}],
            )
            reply = msg.content[0].text if msg.content else ""
        else:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=16,
            )
            reply = resp.choices[0].message.content or ""

        return {"ok": True, "message": f"连接成功，模型回复：{reply[:50]}"}
    except Exception as e:
        return {"ok": False, "message": f"连接失败：{e}"}
