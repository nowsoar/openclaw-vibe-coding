"""配置加载"""
import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AIConfig:
    default_model: str = "gpt-4o-mini"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    task_models: dict = field(default_factory=dict)  # 各任务类型对应的模型
    cost_limit_usd: float = 5.0

    def model_for(self, task_type: str) -> str:
        """获取指定任务类型的模型，没有则用默认值"""
        return self.task_models.get(task_type, self.default_model)


@dataclass
class CacheConfig:
    enabled: bool = True
    ttl_days: int = 3
    dir: str = "~/.researchkit/cache/"


@dataclass
class GlobalConfig:
    ai: AIConfig = field(default_factory=AIConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    output_dir: str = "~/Documents/research/"
    auth: dict = field(default_factory=dict)


def _resolve_env_vars(value: str) -> str:
    """解析 ${ENV_VAR} 格式的环境变量引用"""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        var_name = value[2:-1]
        return os.environ.get(var_name, "")
    return value


def load_global_config(path: Optional[Path] = None) -> GlobalConfig:
    """加载全局配置，默认从 ~/.researchkit/config.yaml"""
    if path is None:
        path = Path.home() / ".researchkit" / "config.yaml"

    if not path.exists():
        return GlobalConfig()

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    ai_data = data.get("ai", {})
    ai_config = AIConfig(
        default_model=ai_data.get("default_model", "gpt-4o-mini"),
        api_key=_resolve_env_vars(ai_data.get("api_key", "")),
        base_url=ai_data.get("base_url", "https://api.openai.com/v1"),
        task_models=ai_data.get("task_models", {}),
        cost_limit_usd=float(ai_data.get("cost_limit_usd", 5.0)),
    )

    cache_data = data.get("cache", {})
    cache_config = CacheConfig(
        enabled=cache_data.get("enabled", True),
        ttl_days=int(cache_data.get("ttl_days", 3)),
    )

    return GlobalConfig(
        ai=ai_config,
        cache=cache_config,
        output_dir=data.get("output", {}).get("dir", "~/Documents/research/"),
        auth=data.get("auth", {}),
    )


def load_task_config(path: Path) -> dict:
    """加载调研任务 YAML 文件"""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_sources_config(path: Optional[Path] = None) -> dict:
    """加载数据源库配置，默认从 ~/.researchkit/sources.yaml"""
    if path is None:
        path = Path.home() / ".researchkit" / "sources.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
