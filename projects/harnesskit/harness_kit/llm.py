"""LLM client module — OpenAI API-compatible interface with configurable base_url."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Generator, Iterator


@dataclass
class LLMConfig:
    """Configuration for an LLM call."""

    model: str = "gpt-4o"
    base_url: str | None = None  # None → uses SDK default (api.openai.com)
    api_key: str | None = None   # None → reads OPENAI_API_KEY env var
    temperature: float = 0.7
    max_tokens: int | None = None

    @classmethod
    def from_harness_config(cls, config: dict[str, Any], overrides: dict[str, Any] | None = None) -> "LLMConfig":
        """Build an LLMConfig from .harness/config.yaml dict + optional overrides."""
        overrides = overrides or {}
        model = overrides.get("model") or config.get("default_model", "gpt-4o")
        base_url = overrides.get("base_url") or config.get("base_url") or os.environ.get("OPENAI_BASE_URL")
        api_key_ref = config.get("api_key", "${OPENAI_API_KEY}")
        if api_key_ref and api_key_ref.startswith("${") and api_key_ref.endswith("}"):
            env_var = api_key_ref[2:-1]
            api_key = os.environ.get(env_var)
        else:
            api_key = api_key_ref or None
        api_key = overrides.get("api_key") or api_key
        temperature = float(overrides.get("temperature", config.get("temperature", 0.7)))
        max_tokens = overrides.get("max_tokens") or config.get("max_tokens")
        return cls(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )


@dataclass
class LLMResponse:
    """Result from a single LLM call."""

    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    duration: float = 0.0
    finish_reason: str = "stop"
    raw: dict[str, Any] = field(default_factory=dict)


def _render_template(template: str, vars: dict[str, str]) -> str:
    """Render a template string with variable substitution.

    Uses Jinja2 if available (SilentUndefined keeps unresolved vars as-is),
    otherwise falls back to simple {{key}} string replacement.
    """
    if not vars:
        return template
    try:
        from jinja2 import Environment, Undefined

        class SilentUndefined(Undefined):
            def __str__(self) -> str:
                return f"{{{{{self._undefined_name}}}}}"

        env = Environment(undefined=SilentUndefined)
        return env.from_string(template).render(**vars)
    except Exception:
        result = template
        for k, v in vars.items():
            result = result.replace("{{" + k + "}}", str(v))
        return result


def build_messages(
    skill_data: dict[str, Any],
    rendered: dict[str, str],
    vars: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Assemble the messages list for an LLM call from a rendered skill.

    Priority:
      - system: system prompt rendered with vars + injected soft rules
      - user: user prompt rendered with vars + context template rendered with vars
    """
    vars = vars or {}
    messages: list[dict[str, str]] = []

    # --- System message ---
    system_parts: list[str] = []
    if rendered.get("system"):
        system_parts.append(_render_template(rendered["system"], vars))

    # Inject soft rules into system prompt
    rules_text = rendered.get("rules", "")
    if rules_text:
        for line in rules_text.splitlines():
            if line.startswith("[soft]"):
                # "规则：{description}"
                rule_desc = line[len("[soft]"):].strip()
                if ":" in rule_desc:
                    rule_desc = rule_desc.split(":", 1)[1].strip()
                system_parts.append(f"规则：{rule_desc}")

    if system_parts:
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})

    # --- User message ---
    user_parts: list[str] = []
    user_template = rendered.get("user", "")
    if user_template:
        user_parts.append(_render_template(user_template, vars))

    # Render context template with vars at call-time (not at save-time)
    context_template = rendered.get("context", "")
    if context_template:
        user_parts.append(_render_template(context_template, vars))

    # If no user template at all, build from vars
    if not user_parts and vars:
        user_parts.append("\n".join(f"{k}: {v}" for k, v in vars.items()))

    if user_parts:
        messages.append({"role": "user", "content": "\n\n".join(user_parts)})

    return messages


def call_llm(
    messages: list[dict[str, str]],
    config: LLMConfig,
    stream: bool = False,
) -> LLMResponse | Generator[str, None, LLMResponse]:
    """Call LLM via OpenAI-compatible API.

    If stream=False: returns an LLMResponse.
    If stream=True: returns a generator that yields text chunks; the final
        StopIteration value is the LLMResponse with token counts.

    Raises ImportError if the 'openai' package is not installed.
    Raises openai.OpenAIError (or subclass) on API errors.
    """
    try:
        import openai
    except ImportError as exc:
        raise ImportError(
            "The 'openai' package is required for LLM calls. "
            "Install it with: pip install openai"
        ) from exc

    client_kwargs: dict[str, Any] = {}
    if config.base_url:
        client_kwargs["base_url"] = config.base_url
    if config.api_key:
        client_kwargs["api_key"] = config.api_key

    client = openai.OpenAI(**client_kwargs)

    call_kwargs: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
    }
    if config.max_tokens:
        call_kwargs["max_tokens"] = config.max_tokens

    if not stream:
        t0 = time.perf_counter()
        response = client.chat.completions.create(**call_kwargs)
        duration = time.perf_counter() - t0
        choice = response.choices[0]
        usage = response.usage
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            duration=duration,
            finish_reason=choice.finish_reason or "stop",
            raw={"id": response.id},
        )
    else:
        return _stream_llm(client, call_kwargs, config)


def _stream_llm(
    client: Any,
    call_kwargs: dict[str, Any],
    config: LLMConfig,
) -> Generator[str, None, LLMResponse]:
    """Internal streaming generator. Yields text chunks, returns LLMResponse."""
    t0 = time.perf_counter()
    chunks: list[str] = []
    finish_reason = "stop"
    model_used = config.model

    with client.chat.completions.create(**call_kwargs, stream=True) as stream:
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                chunks.append(delta.content)
                yield delta.content
            if chunk.choices and chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason
            if hasattr(chunk, "model") and chunk.model:
                model_used = chunk.model

    duration = time.perf_counter() - t0
    full_content = "".join(chunks)

    # Token counts are not available in streaming mode without usage field
    # Some providers include usage in the last chunk
    return LLMResponse(
        content=full_content,
        model=model_used,
        input_tokens=0,
        output_tokens=0,
        duration=duration,
        finish_reason=finish_reason,
    )
